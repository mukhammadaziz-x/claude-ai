# ============================================================
# HotelOS — Shared Configuration
# All services import constants from here
# ============================================================

# ---------- Redis ----------
REDIS_URL = "redis://localhost:6379"

# ---------- Service Ports ----------
RECEPTION_PORT    = 8001
HOUSEKEEPING_PORT = 8002
ROOM_SERVICE_PORT = 8003
MAINTENANCE_PORT  = 8004
DASHBOARD_PORT    = 8000

# ---------- Auth ----------
DASHBOARD_SECRET_KEY = "hotelos-secret-2026"
DASHBOARD_USERNAME   = "admin"
DASHBOARD_PASSWORD   = "admin123"
TOKEN_EXPIRE_MINUTES = 60

# ---------- Hotel Setup ----------
TOTAL_FLOORS = 2
ROOMS_PER_FLOOR = 5   # 10 rooms total: 101-105 (floor 1), 201-205 (floor 2)

ROOM_TYPES   = ["single", "double", "suite", "accessible"]
ROOM_RATES   = {
    "single":     80.0,
    "double":    120.0,
    "suite":     250.0,
    "accessible": 90.0,
}

# Initial room inventory: room_number -> {type, floor, near_elevator, near_stairs}
INITIAL_ROOMS = {
    101: {"type": "single",     "floor": 1, "near_elevator": True,  "near_stairs": False},
    102: {"type": "double",     "floor": 1, "near_elevator": False, "near_stairs": True},
    103: {"type": "suite",      "floor": 1, "near_elevator": False, "near_stairs": False},
    104: {"type": "accessible", "floor": 1, "near_elevator": True,  "near_stairs": False},
    105: {"type": "single",     "floor": 1, "near_elevator": False, "near_stairs": True},
    201: {"type": "double",     "floor": 2, "near_elevator": True,  "near_stairs": False},
    202: {"type": "suite",      "floor": 2, "near_elevator": False, "near_stairs": False},
    203: {"type": "single",     "floor": 2, "near_elevator": False, "near_stairs": True},
    204: {"type": "double",     "floor": 2, "near_elevator": True,  "near_stairs": False},
    205: {"type": "accessible", "floor": 2, "near_elevator": False, "near_stairs": True},
}

# ---------- Room Status Values ----------
STATUS_CLEAN         = "Clean"
STATUS_DIRTY         = "Dirty"
STATUS_BEING_CLEANED = "Being Cleaned"
STATUS_OCCUPIED      = "Occupied"
STATUS_MAINTENANCE   = "Maintenance"

# ---------- Maintenance Urgency ----------
URGENCY_CRITICAL = "Critical"
URGENCY_HIGH     = "High"
URGENCY_NORMAL   = "Normal"
URGENCY_LOW      = "Low"

URGENCY_PRIORITY = {
    URGENCY_CRITICAL: 1,
    URGENCY_HIGH:     2,
    URGENCY_NORMAL:   3,
    URGENCY_LOW:      4,
}

# ---------- Order Status ----------
ORDER_RECEIVED  = "Received"
ORDER_PREPARING = "Preparing"
ORDER_DELIVERY  = "Out for Delivery"
ORDER_DELIVERED = "Delivered"

ORDER_STATES = [ORDER_RECEIVED, ORDER_PREPARING, ORDER_DELIVERY, ORDER_DELIVERED]

# ---------- Technicians ----------
TECHNICIANS = ["Tech-1", "Tech-2", "Tech-3"]
