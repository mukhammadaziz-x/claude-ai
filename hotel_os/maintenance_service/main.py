# ============================================================
# HotelOS — Maintenance Service  (port 8004)
#
# Responsibilities:
#   • Accept issue reports with urgency level (Critical/High/Normal/Low)
#   • Priority Queue Algorithm: assign issues to technicians in order
#   • POST /requests           → submit a new maintenance request
#   • POST /requests/resolve   → technician marks issue as resolved
#   • GET  /requests           → list all requests (sorted by priority)
#   • GET  /requests/open      → open requests only
#   • Publishes events for each new request and resolution
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
    MAINTENANCE_PORT, URGENCY_PRIORITY, TECHNICIANS,
    STATUS_MAINTENANCE, STATUS_DIRTY,
)
from shared import events as Events
from broker.broker import broker

from maintenance_service.models import (
    MaintenanceRequest,
    NewRequestSchema,
    ResolveRequestSchema,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("hotelos.maintenance")

# ------------------------------------------------------------------
# In-memory state
# ------------------------------------------------------------------
request_store: dict[str, MaintenanceRequest] = {}   # request_id → request
technician_busy: dict[str, bool] = {t: False for t in TECHNICIANS}


# ------------------------------------------------------------------
# Priority Queue Algorithm
#
# Step-by-step:
# 1. Collect all Open requests.
# 2. Sort by (priority ASC, submitted_at ASC):
#    - Lower priority number = more urgent → comes first.
#    - Among same urgency, earlier submission comes first (FIFO).
# 3. Find first available (not busy) technician.
# 4. Assign the highest-priority open request to that technician.
# 5. If no technician is free, request stays in queue until one frees up.
# ------------------------------------------------------------------

def _get_next_available_technician() -> str | None:
    """Return the name of the first free technician, or None."""
    for tech, busy in technician_busy.items():
        if not busy:
            return tech
    return None


def _sorted_open_requests() -> list[MaintenanceRequest]:
    """
    Return all Open requests sorted by:
    1. priority ASC  (Critical=1 first)
    2. submitted_at ASC (FIFO within same urgency)
    """
    return sorted(
        [r for r in request_store.values() if r.status == "Open"],
        key=lambda r: (r.priority, r.submitted_at),
    )


async def _try_assign_next() -> None:
    """
    Attempt to assign the highest-priority open request
    to the next available technician.
    Called whenever a new request is submitted or a technician
    becomes free after resolving an issue.
    """
    tech = _get_next_available_technician()
    if tech is None:
        logger.info("All technicians busy — request queued")
        return

    open_requests = _sorted_open_requests()
    if not open_requests:
        return

    top = open_requests[0]
    top.status      = "In Progress"
    top.assigned_to = tech
    technician_busy[tech] = True

    await broker.publish(Events.MAINTENANCE_UPDATED, {
        "request_id":  top.request_id,
        "room_number": top.room_number,
        "urgency":     top.urgency,
        "status":      "In Progress",
        "assigned_to": tech,
        "timestamp":   datetime.utcnow().isoformat(),
    })

    logger.info(
        "Assigned request %s (urgency=%s, room=%d) to %s",
        top.request_id, top.urgency, top.room_number, tech,
    )


# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.connect()
    logger.info("Maintenance Service started on port %d", MAINTENANCE_PORT)
    yield
    await broker.disconnect()
    logger.info("Maintenance Service stopped")


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------

app = FastAPI(
    title="HotelOS — Maintenance Service",
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
    return {"service": "maintenance", "status": "ok"}


@app.get("/requests")
async def list_requests():
    """Return all requests sorted by priority (Critical first)."""
    sorted_reqs = sorted(
        request_store.values(),
        key=lambda r: (r.priority, r.submitted_at),
    )
    return [r.to_dict() for r in sorted_reqs]


@app.get("/requests/open")
async def list_open_requests():
    """Return only open (unresolved) requests sorted by priority."""
    return [r.to_dict() for r in _sorted_open_requests()]


@app.get("/technicians")
async def list_technicians():
    """Return technician availability."""
    return [
        {"name": t, "busy": b}
        for t, b in technician_busy.items()
    ]


@app.post("/requests", status_code=status.HTTP_201_CREATED)
async def submit_request(req: NewRequestSchema):
    """
    Submit a new maintenance request.
    - Validates room number and urgency.
    - Assigns priority score.
    - Publishes maintenance.new_request event.
    - Triggers priority queue assignment.
    """
    # Input validation
    if req.room_number < 100 or req.room_number > 999:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Room number must be between 100 and 999.",
        )

    request_id = f"MNT-{str(uuid.uuid4())[:6].upper()}"
    priority   = URGENCY_PRIORITY.get(req.urgency, 4)

    request = MaintenanceRequest(
        request_id=request_id,
        room_number=req.room_number,
        description=req.description,
        urgency=req.urgency,
        priority=priority,
    )
    request_store[request_id] = request

    await broker.publish(Events.MAINTENANCE_NEW, {
        "request_id":  request_id,
        "room_number": req.room_number,
        "description": req.description,
        "urgency":     req.urgency,
        "priority":    priority,
        "status":      "Open",
        "timestamp":   datetime.utcnow().isoformat(),
    })

    logger.info(
        "New maintenance request %s | room=%d urgency=%s",
        request_id, req.room_number, req.urgency,
    )

    # Trigger priority-queue assignment
    await _try_assign_next()

    return {"message": "Maintenance request submitted", "request": request.to_dict()}


@app.post("/requests/resolve")
async def resolve_request(req: ResolveRequestSchema):
    """
    Technician resolves a maintenance issue.
    - Status → Resolved
    - Technician becomes available again
    - Triggers next priority-queue assignment
    """
    if req.request_id not in request_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request '{req.request_id}' not found.",
        )

    request = request_store[req.request_id]

    if request.status == "Resolved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request '{req.request_id}' is already resolved.",
        )

    tech = request.assigned_to
    request.status      = "Resolved"
    request.resolved_at = datetime.utcnow()
    request.resolution  = req.resolution

    # Free up the technician
    if tech and tech in technician_busy:
        technician_busy[tech] = False

    await broker.publish(Events.MAINTENANCE_UPDATED, {
        "request_id":  req.request_id,
        "room_number": request.room_number,
        "urgency":     request.urgency,
        "status":      "Resolved",
        "resolved_by": tech,
        "resolution":  req.resolution,
        "timestamp":   datetime.utcnow().isoformat(),
    })

    logger.info("Request %s resolved by %s", req.request_id, tech)

    # Try to assign the next queued request
    await _try_assign_next()

    return {"message": f"Request {req.request_id} resolved", "request": request.to_dict()}


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=MAINTENANCE_PORT, reload=False)
