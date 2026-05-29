# ============================================================
# HotelOS — Reception Service  (port 8001)
#
# Endpoints:
#   POST /checkin              → assign room, register guest
#   POST /checkout             → calculate bill, publish room.vacated
#   GET  /rooms                → list all rooms with current status
#   GET  /rooms/{number}       → single room detail
#   GET  /guests               → list all current guests
#   POST /rooms/{number}/charge → add room-service charge to guest bill
# ============================================================

import asyncio
import logging
import sys
import os
from contextlib import asynccontextmanager
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from shared.config import (
    RECEPTION_PORT, INITIAL_ROOMS, ROOM_RATES,
    STATUS_OCCUPIED, STATUS_DIRTY, STATUS_CLEAN,
)
from shared import events as Events
from broker.broker import broker, run_subscriber

from reception_service.models import (
    Room, Guest,
    CheckInRequest, CheckOutRequest, BillResponse,
)
from reception_service.algorithms import assign_room
from reception_service.billing import calculate_bill

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("hotelos.reception")

# ------------------------------------------------------------------
# In-memory state (shared across requests within this service)
# ------------------------------------------------------------------
rooms:  dict[int, Room]  = {}
guests: dict[int, Guest] = {}   # room_number → current guest
bills:  dict[str, BillResponse] = {}  # guest_name → last bill


def _init_rooms() -> None:
    """Populate the room inventory from config on startup."""
    for num, cfg in INITIAL_ROOMS.items():
        rooms[num] = Room(
            number=num,
            room_type=cfg["type"],
            floor=cfg["floor"],
            near_elevator=cfg["near_elevator"],
            near_stairs=cfg["near_stairs"],
            rate_per_night=ROOM_RATES[cfg["type"]],
        )
    logger.info("Initialised %d rooms", len(rooms))


# ------------------------------------------------------------------
# Background: listen for room-status changes from Housekeeping
# ------------------------------------------------------------------
async def _handle_room_status(message: dict) -> None:
    """
    When Housekeeping marks a room Clean, update local room record
    so Reception can assign it to the next guest.
    """
    data = message.get("data", {})
    room_number = data.get("room_number")
    new_status  = data.get("status")

    if room_number in rooms and new_status:
        rooms[room_number].status = new_status
        if new_status == STATUS_CLEAN:
            rooms[room_number].cleaned_at = datetime.utcnow()
            rooms[room_number].guest_name = None
        logger.info("Room %d status updated to '%s' (via broker)", room_number, new_status)


# ------------------------------------------------------------------
# Lifespan — connect broker, start listeners
# ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_rooms()
    await broker.connect()
    # Background subscriber: react to housekeeping status changes
    asyncio.create_task(
        run_subscriber(broker, [Events.ROOM_STATUS_CHANGED], _handle_room_status)
    )
    logger.info("Reception Service started on port %d", RECEPTION_PORT)
    yield
    await broker.disconnect()
    logger.info("Reception Service stopped")


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
app = FastAPI(
    title="HotelOS — Reception Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"service": "reception", "status": "ok"}


@app.get("/rooms")
async def list_rooms():
    """Return current status of all rooms."""
    return [r.to_dict() for r in rooms.values()]


@app.get("/rooms/{room_number}")
async def get_room(room_number: int):
    """Return details for a single room."""
    # ── Input validation ────────────────────────────────────────────
    if room_number not in rooms:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room {room_number} does not exist. Valid rooms: {sorted(rooms.keys())}",
        )
    return rooms[room_number].to_dict()


@app.get("/guests")
async def list_guests():
    """Return all currently checked-in guests."""
    return [g.to_dict() for g in guests.values()]


@app.post("/checkin", status_code=status.HTTP_201_CREATED)
async def check_in(req: CheckInRequest):
    """
    Check in a guest:
    1. Run room assignment algorithm.
    2. Mark room as Occupied.
    3. Register guest record.
    4. Publish guest.checked_in event.
    """
    # ── TS-07: no rooms available ───────────────────────────────────
    best_room = assign_room(
        rooms,
        req.room_type,
        req.floor_preference,
        req.proximity_pref,
    )

    if best_room is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "no_rooms_available",
                "message": (
                    f"No '{req.room_type}' rooms are available right now. "
                    "Please try a different room type or check back later."
                ),
                "suggestion": "Ask front desk for alternative room types or join the waitlist.",
            },
        )

    # ── Assign room ─────────────────────────────────────────────────
    best_room.status     = STATUS_OCCUPIED
    best_room.guest_name = req.guest_name
    guest = Guest(
        name=req.guest_name,
        room_number=best_room.number,
        nights=req.nights,
        discount_pct=req.discount_pct,
        floor_preference=req.floor_preference,
        proximity_pref=req.proximity_pref,
    )
    guests[best_room.number] = guest

    # ── Publish event ────────────────────────────────────────────────
    await broker.publish(Events.GUEST_CHECKED_IN, {
        "guest_name":  req.guest_name,
        "room_number": best_room.number,
        "room_type":   best_room.room_type,
        "floor":       best_room.floor,
        "nights":      req.nights,
        "timestamp":   datetime.utcnow().isoformat(),
    })

    logger.info("Checked in: %s → Room %d", req.guest_name, best_room.number)
    return {
        "message":     "Check-in successful",
        "guest_name":  req.guest_name,
        "room_number": best_room.number,
        "room_type":   best_room.room_type,
        "floor":       best_room.floor,
        "nights":      req.nights,
        "rate_per_night": best_room.rate_per_night,
    }


@app.post("/checkout")
async def check_out(req: CheckOutRequest):
    """
    Check out a guest:
    1. Validate room number and occupancy.
    2. Calculate bill.
    3. Mark room Dirty.
    4. Publish room.vacated and guest.checked_out events.
    """
    # ── TS-08: invalid room number ──────────────────────────────────
    if req.room_number not in rooms:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room {req.room_number} does not exist.",
        )

    room = rooms[req.room_number]

    if req.room_number not in guests:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Room {req.room_number} has no checked-in guest.",
        )

    guest = guests[req.room_number]

    # ── Calculate bill ───────────────────────────────────────────────
    bill = calculate_bill(
        guest,
        rate_per_night=room.rate_per_night,
        early_checkout=req.early_checkout,
        late_fee=req.late_fee,
    )
    bills[guest.name] = bill

    # ── Update room state ────────────────────────────────────────────
    guest.check_out  = datetime.utcnow()
    room.status      = STATUS_DIRTY
    room.guest_name  = None
    del guests[req.room_number]

    # ── Publish events ───────────────────────────────────────────────
    await broker.publish(Events.ROOM_VACATED, {
        "room_number": req.room_number,
        "room_type":   room.room_type,
        "floor":       room.floor,
        "timestamp":   datetime.utcnow().isoformat(),
    })
    await broker.publish(Events.GUEST_CHECKED_OUT, {
        "guest_name":  guest.name,
        "room_number": req.room_number,
        "grand_total": bill.grand_total,
        "timestamp":   datetime.utcnow().isoformat(),
    })

    logger.info("Checked out: %s from Room %d | Total: $%.2f", guest.name, req.room_number, bill.grand_total)
    return {"message": "Check-out successful", "bill": bill.model_dump()}


@app.post("/rooms/{room_number}/charge")
async def add_charge(room_number: int, description: str, amount: float):
    """Add a room-service charge to the guest's running bill."""
    if room_number not in rooms:
        raise HTTPException(status_code=404, detail=f"Room {room_number} not found.")
    if room_number not in guests:
        raise HTTPException(status_code=400, detail=f"No guest in room {room_number}.")
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Charge amount must be greater than 0.")

    guests[room_number].add_room_service_charge(description, round(amount, 2))
    return {"message": "Charge added", "room": room_number, "description": description, "amount": amount}


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=RECEPTION_PORT, reload=False)
