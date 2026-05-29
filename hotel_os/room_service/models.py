# ============================================================
# HotelOS — Room Service: Data Models
# ============================================================

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ------------------------------------------------------------------
# Order Item
# ------------------------------------------------------------------

@dataclass
class OrderItem:
    name:     str
    quantity: int
    price:    float

    def subtotal(self) -> float:
        return round(self.quantity * self.price, 2)

    def to_dict(self) -> dict:
        return {
            "name":     self.name,
            "quantity": self.quantity,
            "price":    self.price,
            "subtotal": self.subtotal(),
        }


# ------------------------------------------------------------------
# Order
# ------------------------------------------------------------------

@dataclass
class Order:
    """
    Represents a room-service order.

    States: Received → Preparing → Out for Delivery → Delivered
    """

    order_id:    str
    room_number: int
    items:       list[OrderItem]
    status:      str = "Received"
    created_at:  datetime = field(default_factory=datetime.utcnow)
    updated_at:  datetime = field(default_factory=datetime.utcnow)
    total:       float = 0.0

    def __post_init__(self):
        self.total = round(sum(i.subtotal() for i in self.items), 2)

    def to_dict(self) -> dict:
        return {
            "order_id":    self.order_id,
            "room_number": self.room_number,
            "items":       [i.to_dict() for i in self.items],
            "status":      self.status,
            "created_at":  self.created_at.isoformat(),
            "updated_at":  self.updated_at.isoformat(),
            "total":       self.total,
        }


# ------------------------------------------------------------------
# Pydantic schemas
# ------------------------------------------------------------------

class OrderItemRequest(BaseModel):
    name:     str   = Field(..., min_length=1, max_length=100)
    quantity: int   = Field(..., ge=1, le=20)
    price:    float = Field(..., gt=0)


class NewOrderRequest(BaseModel):
    room_number: int              = Field(..., ge=100, le=999)
    items:       list[OrderItemRequest] = Field(..., min_length=1)

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v):
        if not v:
            raise ValueError("Order must contain at least one item.")
        return v


class UpdateOrderRequest(BaseModel):
    order_id: str = Field(..., min_length=1)
