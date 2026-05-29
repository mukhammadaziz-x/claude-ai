# ============================================================
# HotelOS — Housekeeping Service: Data Models
# ============================================================

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# Cleaning Task
# ------------------------------------------------------------------

@dataclass
class CleaningTask:
    """
    Represents one room-cleaning job in the queue.

    Attributes:
        room_number  : room to be cleaned
        room_type    : type of room (for workload estimation)
        floor        : floor number
        status       : 'Pending' | 'Being Cleaned' | 'Clean'
        assigned_to  : housekeeper name (None if not yet assigned)
        queued_at    : when the task was added to the queue
        started_at   : when a housekeeper started cleaning
        completed_at : when the room was marked Clean
    """

    room_number:  int
    room_type:    str
    floor:        int
    status:       str = "Pending"
    assigned_to:  Optional[str] = None
    queued_at:    datetime = field(default_factory=datetime.utcnow)
    started_at:   Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "room_number":  self.room_number,
            "room_type":    self.room_type,
            "floor":        self.floor,
            "status":       self.status,
            "assigned_to":  self.assigned_to,
            "queued_at":    self.queued_at.isoformat(),
            "started_at":   self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ------------------------------------------------------------------
# Pydantic schemas
# ------------------------------------------------------------------

class StartCleaningRequest(BaseModel):
    room_number: int   = Field(..., ge=100, le=999)
    housekeeper: str   = Field(..., min_length=2, max_length=60)


class CompleteCleaningRequest(BaseModel):
    room_number: int   = Field(..., ge=100, le=999)
