# ============================================================
# HotelOS — Event / Channel Names for Redis Pub/Sub
#
# Table of all broker events:
# ┌─────────────────────────────┬─────────────────┬──────────────────────────────┐
# │ Event Name                  │ Publisher       │ Subscriber(s)                │
# ├─────────────────────────────┼─────────────────┼──────────────────────────────┤
# │ room.vacated                │ Reception       │ Housekeeping, Dashboard      │
# │ room.status_changed         │ Housekeeping    │ Dashboard, Reception         │
# │ room.assigned               │ Reception       │ Dashboard                    │
# │ guest.checked_in            │ Reception       │ Dashboard                    │
# │ guest.checked_out           │ Reception       │ Dashboard                    │
# │ order.state_changed         │ Room Service    │ Dashboard                    │
# │ order.new                   │ Room Service    │ Dashboard                    │
# │ maintenance.new_request     │ Maintenance     │ Dashboard                    │
# │ maintenance.status_changed  │ Maintenance     │ Dashboard                    │
# │ hotelos.broadcast           │ Any service     │ Dashboard (WebSocket push)   │
# └─────────────────────────────┴─────────────────┴──────────────────────────────┘
# ============================================================

# Reception events
ROOM_VACATED        = "room.vacated"
ROOM_ASSIGNED       = "room.assigned"
GUEST_CHECKED_IN    = "guest.checked_in"
GUEST_CHECKED_OUT   = "guest.checked_out"

# Housekeeping events
ROOM_STATUS_CHANGED = "room.status_changed"

# Room Service events
ORDER_NEW           = "order.new"
ORDER_STATE_CHANGED = "order.state_changed"

# Maintenance events
MAINTENANCE_NEW     = "maintenance.new_request"
MAINTENANCE_UPDATED = "maintenance.status_changed"

# General broadcast to dashboard WebSocket clients
BROADCAST           = "hotelos.broadcast"
