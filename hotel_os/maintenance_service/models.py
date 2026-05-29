# ============================================================
# HotelOS — Maintenance Service: Data Models
# ============================================================

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# Maintenance Request
# ------------------------------------------------------------------

@dataclass
class MaintenanceRequest:
    """
    Represents a maintenance issue report.

    Urgency levels (priority order):
        Critical → 1  (safety hazard, elevator fault)
        High     → 2  (broken shower, no hot water)
        Normal   → 3  (noisy AC, TV issue)
        Low      → 4  (light bulb, cosmetic damage)

    If two requests share the same urgency, the one submitted first
    takes priority (FIFO within same urgency level).

    States: Open → In Progress → Resolved
    """

    request_id:   str
    room_number:  int
    description:  str
    urgency:      str           # Critical | High | Normal | Low
    priority:     int           # 1–4 (lower = more urgent)
    status:       str = "Open"
    assigned_to:  Optional[str] = None
    submitted_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at:  Optional[datetime] = None
    resolution:   Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "request_id":   self.request_id,
            "room_number":  self.room_number,
            "description":  self.description,
            "urgency":      self.urgency,
            "priority":     self.priority,
            "status":       self.status,
            "assigned_to":  self.assigned_to,
            "submitted_at": self.submitted_at.isoformat(),
            "resolved_at":  self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution":   self.resolution,
        }


# ------------------------------------------------------------------
# Pydantic schemas
# ------------------------------------------------------------------

class NewRequestSchema(BaseModel):
    room_number:  int = Field(..., ge=100, le=999)
    description:  str = Field(..., min_length=5, max_length=300)
    urgency:      str = Field(..., pattern="^(Critical|High|Normal|Low)$")


class ResolveRequestSchema(BaseModel):
    request_id: str = Field(..., min_length=1)
    resolution: str = Field(..., min_length=5, max_length=300)
