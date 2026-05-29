# ============================================================
# HotelOS — Reception Service: Data Models
# ============================================================

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from shared.config import STATUS_CLEAN


# ------------------------------------------------------------------
# Room
# ------------------------------------------------------------------

@dataclass
class Room:
    """
    Represents a single hotel room and its current state.

    Attributes:
        number        : unique room number (e.g. 101, 204)
        room_type     : 'single' | 'double' | 'suite' | 'accessible'
        floor         : floor number (1 or 2)
        near_elevator : True if the room is close to the elevator
        near_stairs   : True if the room is close to the stairs
        status        : current housekeeping/occupancy status
        cleaned_at    : timestamp of the last time status was set to 'Clean'
        guest_name    : name of the current guest (None if vacant)
        rate_per_night: nightly room rate in USD
    """

    number:         int
    room_type:      str
    floor:          int
    near_elevator:  bool = False
    near_stairs:    bool = False
    status:         str  = STATUS_CLEAN
    cleaned_at:     datetime = field(default_factory=datetime.utcnow)
    guest_name:     Optional[str] = None
    rate_per_night: float = 0.0

    def is_available(self) -> bool:
        """A room is available only when it is Clean and unoccupied."""
        return self.status == STATUS_CLEAN and self.guest_name is None

    def to_dict(self) -> dict:
        return {
            "number":         self.number,
            "room_type":      self.room_type,
            "floor":          self.floor,
            "near_elevator":  self.near_elevator,
            "near_stairs":    self.near_stairs,
            "status":         self.status,
            "cleaned_at":     self.cleaned_at.isoformat(),
            "guest_name":     self.guest_name,
            "rate_per_night": self.rate_per_night,
        }


# ------------------------------------------------------------------
# Guest
# ------------------------------------------------------------------

@dataclass
class Guest:
    """
    Represents a hotel guest and their current stay.

    Attributes:
        name            : full name of the guest
        room_number     : assigned room number
        check_in        : check-in datetime
        check_out       : check-out datetime (None until checkout)
        nights          : number of nights booked
        room_service_charges : list of {description, amount} dicts
        extra_charges   : list of {description, amount} dicts (minibar, late checkout, etc.)
        discount_pct    : discount percentage (0–100)
        floor_preference: preferred floor (None means no preference)
        proximity_pref  : 'elevator' | 'stairs' | None
    """

    name:                  str
    room_number:           int
    check_in:              datetime = field(default_factory=datetime.utcnow)
    check_out:             Optional[datetime] = None
    nights:                int = 1
    room_service_charges:  list = field(default_factory=list)
    extra_charges:         list = field(default_factory=list)
    discount_pct:          float = 0.0
    floor_preference:      Optional[int] = None
    proximity_pref:        Optional[str] = None  # 'elevator' | 'stairs'

    def add_room_service_charge(self, description: str, amount: float) -> None:
        """Append a room-service charge to the guest's bill."""
        self.room_service_charges.append({"description": description, "amount": amount})

    def add_extra_charge(self, description: str, amount: float) -> None:
        """Append a miscellaneous extra charge (minibar, late checkout, etc.)."""
        self.extra_charges.append({"description": description, "amount": amount})

    def to_dict(self) -> dict:
        return {
            "name":                  self.name,
            "room_number":           self.room_number,
            "check_in":              self.check_in.isoformat(),
            "check_out":             self.check_out.isoformat() if self.check_out else None,
            "nights":                self.nights,
            "room_service_charges":  self.room_service_charges,
            "extra_charges":         self.extra_charges,
            "discount_pct":          self.discount_pct,
            "floor_preference":      self.floor_preference,
            "proximity_pref":        self.proximity_pref,
        }


# ------------------------------------------------------------------
# Pydantic request / response schemas (FastAPI I/O)
# ------------------------------------------------------------------

from pydantic import BaseModel, Field, field_validator


class CheckInRequest(BaseModel):
    guest_name:       str         = Field(..., min_length=2, max_length=100)
    room_type:        str         = Field(..., pattern="^(single|double|suite|accessible)$")
    nights:           int         = Field(..., ge=1, le=365)
    floor_preference: Optional[int]  = Field(None, ge=1, le=2)
    proximity_pref:   Optional[str]  = Field(None, pattern="^(elevator|stairs)$")
    discount_pct:     float          = Field(0.0, ge=0.0, le=100.0)

    @field_validator("guest_name")
    @classmethod
    def name_must_be_clean(cls, v: str) -> str:
        v = v.strip()
        if not v.replace(" ", "").isalpha():
            raise ValueError("Guest name must contain letters only")
        return v


class CheckOutRequest(BaseModel):
    room_number:    int   = Field(..., ge=100, le=999)
    early_checkout: bool  = False
    late_fee:       float = Field(0.0, ge=0.0)


class RoomStatusResponse(BaseModel):
    room_number: int
    status:      str
    guest_name:  Optional[str]
    room_type:   str
    floor:       int


class BillResponse(BaseModel):
    guest_name:           str
    room_number:          int
    nights:               int
    room_rate:            float
    room_total:           float
    room_service_total:   float
    extra_charges_total:  float
    discount_amount:      float
    grand_total:          float
    breakdown:            list
