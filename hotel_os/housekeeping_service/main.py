# ============================================================
# HotelOS — Housekeeping Service  (port 8002)
#
# Responsibilities:
#   • Subscribe to room.vacated  → add room to cleaning queue
#   • POST /cleaning/start       → housekeeper starts cleaning a room
#   • POST /cleaning/complete    → housekeeper marks room as Clean
#   • GET  /queue                → list current cleaning queue
#   • GET  /rooms                → list all room statuses known to housekeeping
#
# Status flow:   Dirty → Being Cleaned → Clean
# Every status change is published to the broker so the Dashboard
# and Reception can react in real time.
# ============================================================

import asyncio
import logging
import sys
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from shared.config import (
    HOUSEKEEPING_PORT, INITIAL_ROOMS,
    STATUS_CLEAN, STATUS_DIRTY, STATUS_BEING_CLEANED, STATUS_OCCUPIED,
)
from shared import events as Events
from broker.broker import broker, run_subscriber

from housekeeping_service.models import (
    CleaningTask,
    StartCleaningRequest,
    CompleteCleaningRequest,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("hotelos.housekeeping")

# ------------------------------------------------------------------
# In-memory state
# ------------------------------------------------------------------
cleaning_queue: list[CleaningTask] = []     # ordered list of pending/active tasks
room_statuses:  dict[int, str] = {}         # room_number → current status


def _init_statuses() -> None:
    """All rooms start as Clean."""
    for num in INITIAL_ROOMS:
        room_statuses[num] = STATUS_CLEAN
    logger.info("Housekeeping: initialised %d room statuses", len(room_statuses))


# ------------------------------------------------------------------
# Broker event handlers
# ------------------------------------------------------------------

async def _handle_room_vacated(message: dict) -> None:
    """
    Reception published room.vacated → add the room to the cleaning queue.
    This is the event-driven link between Reception and Housekeeping.
    """
    data        = message.get("data", {})
    room_number = data.get("room_number")
    room_type   = data.get("room_type", "unknown")
    floor       = data.get("floor", 1)

    if room_number is None:
        return

    # Avoid duplicate entries
    already_queued = any(
        t.room_number == room_number and t.status != STATUS_CLEAN
        for t in cleaning_queue
    )
    if already_queued:
        logger.warning("Room %d already in cleaning queue — skipping duplicate", room_number)
        return

    task = CleaningTask(
        room_number=room_number,
        room_type=room_type,
        floor=floor,
        status="Pending",
    )
    cleaning_queue.append(task)
    room_statuses[room_number] = STATUS_DIRTY

    # Publish status change so dashboard updates instantly
    await broker.publish(Events.ROOM_STATUS_CHANGED, {
        "room_number": room_number,
        "status":      STATUS_DIRTY,
        "timestamp":   datetime.utcnow().isoformat(),
    })

    logger.info("Room %d added to cleaning queue (status → Dirty)", room_number)


# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_statuses()
    await broker.connect()
    asyncio.create_task(
        run_subscriber(broker, [Events.ROOM_VACATED], _handle_room_vacated)
    )
    logger.info("Housekeeping Service started on port %d", HOUSEKEEPING_PORT)
    yield
    await broker.disconnect()
    logger.info("Housekeeping Service stopped")


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------

app = FastAPI(
    title="HotelOS — Housekeeping Service",
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
    return {"service": "housekeeping", "status": "ok"}


@app.get("/queue")
async def get_queue():
    """Return the current cleaning queue (all tasks)."""
    return [t.to_dict() for t in cleaning_queue]


@app.get("/rooms")
async def get_room_statuses():
    """Return housekeeping's view of all room statuses."""
    return [{"room_number": k, "status": v} for k, v in room_statuses.items()]


@app.post("/cleaning/start")
async def start_cleaning(req: StartCleaningRequest):
    """
    Housekeeper starts cleaning a room.
    Status: Dirty → Being Cleaned
    Publishes room.status_changed event.
    """
    # Find pending task for this room
    task = next(
        (t for t in cleaning_queue
         if t.room_number == req.room_number and t.status == "Pending"),
        None,
    )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No pending cleaning task for room {req.room_number}.",
        )

    task.status      = STATUS_BEING_CLEANED
    task.assigned_to = req.housekeeper
    task.started_at  = datetime.utcnow()
    room_statuses[req.room_number] = STATUS_BEING_CLEANED

    await broker.publish(Events.ROOM_STATUS_CHANGED, {
        "room_number": req.room_number,
        "status":      STATUS_BEING_CLEANED,
        "housekeeper": req.housekeeper,
        "timestamp":   datetime.utcnow().isoformat(),
    })

    logger.info("Room %d cleaning started by %s", req.room_number, req.housekeeper)
    return {"message": f"Cleaning started for room {req.room_number}", "task": task.to_dict()}


@app.post("/cleaning/complete")
async def complete_cleaning(req: CompleteCleaningRequest):
    """
    Housekeeper marks room as Clean.
    Status: Being Cleaned → Clean
    Publishes room.status_changed event → Reception can now assign the room.
    Dashboard updates in real time via WebSocket.
    """
    task = next(
        (t for t in cleaning_queue
         if t.room_number == req.room_number and t.status == STATUS_BEING_CLEANED),
        None,
    )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active cleaning task for room {req.room_number}. "
                   f"Make sure cleaning was started first.",
        )

    task.status       = STATUS_CLEAN
    task.completed_at = datetime.utcnow()
    room_statuses[req.room_number] = STATUS_CLEAN

    await broker.publish(Events.ROOM_STATUS_CHANGED, {
        "room_number": req.room_number,
        "status":      STATUS_CLEAN,
        "cleaned_at":  task.completed_at.isoformat(),
        "timestamp":   datetime.utcnow().isoformat(),
    })

    logger.info("Room %d marked Clean by %s", req.room_number, task.assigned_to)
    return {"message": f"Room {req.room_number} is now Clean", "task": task.to_dict()}


@app.post("/rooms/{room_number}/add")
async def manually_add_room(room_number: int, room_type: str = "single", floor: int = 1):
    """Manually add a room to the cleaning queue (for testing / admin use)."""
    if room_number < 100 or room_number > 999:
        raise HTTPException(status_code=422, detail="Invalid room number.")

    task = CleaningTask(
        room_number=room_number,
        room_type=room_type,
        floor=floor,
        status="Pending",
    )
    cleaning_queue.append(task)
    room_statuses[room_number] = STATUS_DIRTY

    await broker.publish(Events.ROOM_STATUS_CHANGED, {
        "room_number": room_number,
        "status":      STATUS_DIRTY,
        "timestamp":   datetime.utcnow().isoformat(),
    })
    return {"message": f"Room {room_number} added to cleaning queue"}


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=HOUSEKEEPING_PORT, reload=False)
