# ============================================================
# HotelOS — Dashboard Service  (port 8000)
#
# Responsibilities:
#   • Serve the operations dashboard HTML/CSS/JS
#   • WebSocket endpoint: push live updates to all connected browsers
#   • Subscribe to ALL broker events → forward to WebSocket clients
#   • REST proxy endpoints so the UI can call services via dashboard
#
# WebSocket flow:
#   Browser → WS connect (with token) → dashboard/main.py
#   Broker event arrives → broadcast to all WS clients → browser updates
#
# Endpoints:
#   GET  /               → dashboard HTML (login gate)
#   POST /auth/login     → returns token
#   WS   /ws             → WebSocket connection (?token=...)
#   GET  /api/rooms      → proxy to Reception
#   GET  /api/orders     → proxy to Room Service
#   GET  /api/requests   → proxy to Maintenance
#   GET  /api/queue      → proxy to Housekeeping
# ============================================================

import asyncio
import logging
import sys
import os
import json
from contextlib import asynccontextmanager
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from shared.config import (
    DASHBOARD_PORT, RECEPTION_PORT, HOUSEKEEPING_PORT,
    ROOM_SERVICE_PORT, MAINTENANCE_PORT,
)
from shared import events as Events
from broker.broker import broker

from dashboard.auth import authenticate, LoginRequest, verify_token, get_current_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("hotelos.dashboard")


# ------------------------------------------------------------------
# WebSocket Connection Manager
# ------------------------------------------------------------------

class ConnectionManager:
    """Manages all active WebSocket connections."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        logger.info("WS client connected. Total: %d", len(self.active))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)
        logger.info("WS client disconnected. Total: %d", len(self.active))

    async def broadcast(self, data: dict) -> None:
        """Send a message to all connected clients. Remove dead connections."""
        dead = []
        message = json.dumps(data)
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_personal(self, ws: WebSocket, data: dict) -> None:
        try:
            await ws.send_text(json.dumps(data))
        except Exception:
            self.disconnect(ws)


manager = ConnectionManager()


# ------------------------------------------------------------------
# Background broker subscriber → WebSocket broadcast
# ------------------------------------------------------------------

ALL_CHANNELS = [
    Events.ROOM_VACATED,
    Events.ROOM_STATUS_CHANGED,
    Events.ROOM_ASSIGNED,
    Events.GUEST_CHECKED_IN,
    Events.GUEST_CHECKED_OUT,
    Events.ORDER_NEW,
    Events.ORDER_STATE_CHANGED,
    Events.MAINTENANCE_NEW,
    Events.MAINTENANCE_UPDATED,
    Events.BROADCAST,
]


async def _broker_to_websocket() -> None:
    """
    Long-running background task:
    Subscribes to all broker channels and forwards every message
    to all connected WebSocket clients.
    This is the core real-time bridge between services and the browser.
    """
    async for message in broker.subscribe(*ALL_CHANNELS):
        try:
            await manager.broadcast(message)
        except Exception as exc:
            logger.error("WS broadcast error: %s", exc)


# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.connect()
    asyncio.create_task(_broker_to_websocket())
    logger.info("Dashboard Service started on port %d", DASHBOARD_PORT)
    yield
    await broker.disconnect()
    logger.info("Dashboard Service stopped")


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------

app = FastAPI(
    title="HotelOS — Dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (CSS, JS)
_static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(_static_path):
    app.mount("/static", StaticFiles(directory=_static_path), name="static")


# ------------------------------------------------------------------
# Auth endpoints
# ------------------------------------------------------------------

@app.post("/auth/login")
async def login(req: LoginRequest):
    token = authenticate(req.username, req.password)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/health")
async def health():
    return {"service": "dashboard", "status": "ok", "ws_clients": len(manager.active)}


# ------------------------------------------------------------------
# Dashboard HTML — served at root
# ------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard_root():
    html_path = os.path.join(_static_path, "index.html")
    if os.path.exists(html_path):
        with open(html_path) as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Dashboard static files not found</h1>", status_code=500)


# ------------------------------------------------------------------
# WebSocket endpoint
# ------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    token: str = Query(..., description="Auth token"),
):
    """
    WebSocket connection for real-time dashboard updates.

    - Client connects with ?token=<jwt>
    - Server verifies token before accepting
    - On connection: sends full current state snapshot
    - Thereafter: pushes every broker event as JSON
    """
    # Validate token before accepting connection
    try:
        verify_token(token)
    except HTTPException:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(ws)

    # Send initial snapshot so the page is populated immediately
    snapshot = await _build_snapshot()
    await manager.send_personal(ws, {"channel": "snapshot", "data": snapshot})

    try:
        # Keep connection alive — client can send pings
        while True:
            text = await ws.receive_text()
            if text == "ping":
                await ws.send_text(json.dumps({"channel": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ------------------------------------------------------------------
# API proxy endpoints (dashboard UI calls these)
# ------------------------------------------------------------------

async def _fetch(url: str) -> Any:
    """Internal helper: GET request to a microservice."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Proxy fetch failed for %s: %s", url, exc)
        return []


async def _build_snapshot() -> dict:
    """Fetch current state from all services for the initial WS snapshot."""
    rooms    = await _fetch(f"http://localhost:{RECEPTION_PORT}/rooms")
    orders   = await _fetch(f"http://localhost:{ROOM_SERVICE_PORT}/orders")
    requests = await _fetch(f"http://localhost:{MAINTENANCE_PORT}/requests")
    queue    = await _fetch(f"http://localhost:{HOUSEKEEPING_PORT}/queue")
    guests   = await _fetch(f"http://localhost:{RECEPTION_PORT}/guests")
    return {
        "rooms":    rooms,
        "orders":   orders,
        "requests": requests,
        "queue":    queue,
        "guests":   guests,
    }


@app.get("/api/rooms")
async def api_rooms(_=Depends(get_current_user)):
    return await _fetch(f"http://localhost:{RECEPTION_PORT}/rooms")


@app.get("/api/orders")
async def api_orders(_=Depends(get_current_user)):
    return await _fetch(f"http://localhost:{ROOM_SERVICE_PORT}/orders")


@app.get("/api/requests")
async def api_requests(_=Depends(get_current_user)):
    return await _fetch(f"http://localhost:{MAINTENANCE_PORT}/requests")


@app.get("/api/queue")
async def api_queue(_=Depends(get_current_user)):
    return await _fetch(f"http://localhost:{HOUSEKEEPING_PORT}/queue")


@app.get("/api/snapshot")
async def api_snapshot(_=Depends(get_current_user)):
    return await _build_snapshot()


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=DASHBOARD_PORT, reload=False)
