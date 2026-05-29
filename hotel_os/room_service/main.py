# ============================================================
# HotelOS — Room Service  (port 8003)
#
# Responsibilities:
#   • Accept food/drink orders linked to a room number
#   • Progress orders: Received → Preparing → Out for Delivery → Delivered
#   • Publish order state changes so dashboard updates in real time
#   • POST /orders           → place a new order
#   • POST /orders/advance   → advance order to next state
#   • GET  /orders           → list all orders
#   • GET  /orders/{order_id}→ single order detail
#   • Notify reception (via broker) of charges to add to the guest bill
# ============================================================

import asyncio
import logging
import sys
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from shared.config import (
    ROOM_SERVICE_PORT, RECEPTION_PORT,
    ORDER_RECEIVED, ORDER_PREPARING, ORDER_DELIVERY, ORDER_DELIVERED, ORDER_STATES,
)
from shared import events as Events
from broker.broker import broker

from room_service.models import Order, OrderItem, NewOrderRequest, UpdateOrderRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("hotelos.roomservice")

# ------------------------------------------------------------------
# In-memory state
# ------------------------------------------------------------------
orders: dict[str, Order] = {}   # order_id → Order


# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.connect()
    logger.info("Room Service started on port %d", ROOM_SERVICE_PORT)
    yield
    await broker.disconnect()
    logger.info("Room Service stopped")


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------

app = FastAPI(
    title="HotelOS — Room Service",
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
# Helpers
# ------------------------------------------------------------------

def _next_status(current: str) -> str | None:
    """Return the next order state, or None if already Delivered."""
    try:
        idx = ORDER_STATES.index(current)
        if idx + 1 < len(ORDER_STATES):
            return ORDER_STATES[idx + 1]
    except ValueError:
        pass
    return None


async def _notify_reception_charge(room_number: int, description: str, amount: float) -> None:
    """
    Call Reception Service REST endpoint to attach the charge to the guest's bill.
    If Reception is unreachable, log warning — do not crash.
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(
                f"http://localhost:{RECEPTION_PORT}/rooms/{room_number}/charge",
                params={"description": description, "amount": amount},
            )
            if resp.status_code == 200:
                logger.info("Charge added to room %d bill: %s $%.2f", room_number, description, amount)
            else:
                logger.warning("Reception charge response: %d", resp.status_code)
    except Exception as exc:
        logger.warning("Could not notify reception of charge (room %d): %s", room_number, exc)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"service": "room_service", "status": "ok"}


@app.get("/orders")
async def list_orders():
    """Return all orders sorted by creation time (newest first)."""
    return sorted(
        [o.to_dict() for o in orders.values()],
        key=lambda x: x["created_at"],
        reverse=True,
    )


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    if order_id not in orders:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")
    return orders[order_id].to_dict()


@app.post("/orders", status_code=status.HTTP_201_CREATED)
async def place_order(req: NewOrderRequest):
    """
    Place a new room-service order.
    Publishes order.new event → dashboard shows it instantly.
    """
    order_id = str(uuid.uuid4())[:8].upper()

    items = [
        OrderItem(name=i.name, quantity=i.quantity, price=i.price)
        for i in req.items
    ]
    order = Order(
        order_id=order_id,
        room_number=req.room_number,
        items=items,
    )
    orders[order_id] = order

    await broker.publish(Events.ORDER_NEW, {
        "order_id":    order_id,
        "room_number": req.room_number,
        "items":       [i.to_dict() for i in items],
        "total":       order.total,
        "status":      order.status,
        "timestamp":   datetime.utcnow().isoformat(),
    })

    logger.info("New order %s for room %d | total $%.2f", order_id, req.room_number, order.total)
    return {"message": "Order placed", "order": order.to_dict()}


@app.post("/orders/advance")
async def advance_order(req: UpdateOrderRequest):
    """
    Advance an order to the next state.
    States: Received → Preparing → Out for Delivery → Delivered

    On Delivered: charge is posted to Reception for billing.
    """
    if req.order_id not in orders:
        raise HTTPException(status_code=404, detail=f"Order '{req.order_id}' not found.")

    order = orders[req.order_id]

    if order.status == ORDER_DELIVERED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order is already delivered. No further state transitions possible.",
        )

    previous_status = order.status
    next_st = _next_status(order.status)
    if next_st is None:
        raise HTTPException(status_code=400, detail="Cannot advance order status.")

    order.status     = next_st
    order.updated_at = datetime.utcnow()

    await broker.publish(Events.ORDER_STATE_CHANGED, {
        "order_id":        order.order_id,
        "room_number":     order.room_number,
        "previous_status": previous_status,
        "new_status":      next_st,
        "total":           order.total,
        "timestamp":       datetime.utcnow().isoformat(),
    })

    # When delivered → add charge to reception bill
    if next_st == ORDER_DELIVERED:
        desc = f"Room Service Order #{order.order_id}"
        await _notify_reception_charge(order.room_number, desc, order.total)

    logger.info(
        "Order %s advanced: %s → %s (room %d)",
        order.order_id, previous_status, next_st, order.room_number
    )
    return {"message": f"Order advanced to '{next_st}'", "order": order.to_dict()}


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=ROOM_SERVICE_PORT, reload=False)
