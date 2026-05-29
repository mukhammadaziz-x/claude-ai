# HotelOS — Real-Time Hotel Management System

**BTEC Higher Nationals — Unit 4: Programming**
**Assignment: HotelOS: Building a Real-Time Hotel Management System**
**Student: Khabibullayev Muhammadaziz | ID: 240281**

---

## Overview

HotelOS is a microservices-based hotel management system built with **FastAPI**, **Redis Pub/Sub**, and **WebSocket**. It connects four independent departments — Reception, Housekeeping, Room Service, and Maintenance — through a single real-time operations dashboard.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     OPERATIONS DASHBOARD                     │
│              (WebSocket · port 8000 · browser UI)            │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebSocket (real-time push)
┌──────────────────────────▼──────────────────────────────────┐
│                    REDIS PUB/SUB BROKER                      │
│              (all inter-service communication)               │
└────┬──────────────┬──────────────┬───────────────┬──────────┘
     │              │              │               │
┌────▼────┐  ┌──────▼──────┐ ┌────▼────┐  ┌───────▼──────┐
│Reception│  │Housekeeping │ │  Room   │  │ Maintenance  │
│  :8001  │  │    :8002    │ │Service  │  │    :8004     │
│         │  │             │ │  :8003  │  │              │
└─────────┘  └─────────────┘ └─────────┘  └──────────────┘
```

### Services

| Service | Port | Responsibility |
|---|---|---|
| **Dashboard** | 8000 | Operations UI + WebSocket server + Auth |
| **Reception** | 8001 | Check-in, Check-out, Room Assignment, Billing |
| **Housekeeping** | 8002 | Cleaning queue, Room status updates |
| **Room Service** | 8003 | Food/drink orders, Order state progression |
| **Maintenance** | 8004 | Issue reports, Priority queue, Technician assignment |

### Message Broker Events

| Event | Publisher | Subscriber(s) |
|---|---|---|
| `room.vacated` | Reception | Housekeeping, Dashboard |
| `room.status_changed` | Housekeeping | Reception, Dashboard |
| `room.assigned` | Reception | Dashboard |
| `guest.checked_in` | Reception | Dashboard |
| `guest.checked_out` | Reception | Dashboard |
| `order.new` | Room Service | Dashboard |
| `order.state_changed` | Room Service | Dashboard |
| `maintenance.new_request` | Maintenance | Dashboard |
| `maintenance.status_changed` | Maintenance | Dashboard |

---

## Requirements

- **Python 3.11+**
- **Redis 7+** (must be running before starting services)
- All dependencies listed in `requirements.txt`

---

## Installation

### 1. Install Redis

**macOS:**
```bash
brew install redis
brew services start redis
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install redis-server
sudo systemctl start redis
```

**Windows:**
```bash
# Use WSL2 or Docker:
docker run -d -p 6379:6379 redis:7
```

**Verify Redis is running:**
```bash
redis-cli ping   # Should return: PONG
```

### 2. Clone & Install Python Dependencies

```bash
cd hotel_os
pip install -r requirements.txt
```

---

## Running HotelOS

Open **5 separate terminal windows** and run each service:

### Terminal 1 — Dashboard (start this last)
```bash
cd hotel_os
python -m uvicorn dashboard.main:app --host 0.0.0.0 --port 8000
```

### Terminal 2 — Reception Service
```bash
cd hotel_os
python -m uvicorn reception_service.main:app --host 0.0.0.0 --port 8001
```

### Terminal 3 — Housekeeping Service
```bash
cd hotel_os
python -m uvicorn housekeeping_service.main:app --host 0.0.0.0 --port 8002
```

### Terminal 4 — Room Service
```bash
cd hotel_os
python -m uvicorn room_service.main:app --host 0.0.0.0 --port 8003
```

### Terminal 5 — Maintenance Service
```bash
cd hotel_os
python -m uvicorn maintenance_service.main:app --host 0.0.0.0 --port 8004
```

### Access the Dashboard
Open your browser: **http://localhost:8000**

**Login credentials:**
- Username: `admin`
- Password: `admin123`

---

## API Documentation

Each service exposes interactive Swagger docs:

| Service | Swagger UI |
|---|---|
| Dashboard | http://localhost:8000/docs |
| Reception | http://localhost:8001/docs |
| Housekeeping | http://localhost:8002/docs |
| Room Service | http://localhost:8003/docs |
| Maintenance | http://localhost:8004/docs |

---

## Room Inventory (10 rooms, 2 floors)

| Room | Type | Floor | Near Elevator | Near Stairs |
|---|---|---|---|---|
| 101 | Single | 1 | ✓ | |
| 102 | Double | 1 | | ✓ |
| 103 | Suite | 1 | | |
| 104 | Accessible | 1 | ✓ | |
| 105 | Single | 1 | | ✓ |
| 201 | Double | 2 | ✓ | |
| 202 | Suite | 2 | | |
| 203 | Single | 2 | | ✓ |
| 204 | Double | 2 | ✓ | |
| 205 | Accessible | 2 | | ✓ |

---

## Test Scenarios

### TS-01 — Guest check-in (double room, floor 3 preference)
```bash
curl -X POST http://localhost:8001/checkin \
  -H "Content-Type: application/json" \
  -d '{"guest_name":"John Smith","room_type":"double","nights":3,"floor_preference":2}'
```

### TS-02 — Guest check-out from Room 204
```bash
curl -X POST http://localhost:8001/checkout \
  -H "Content-Type: application/json" \
  -d '{"room_number":204,"early_checkout":false,"late_fee":0}'
```

### TS-03 — Housekeeper starts and completes cleaning Room 204
```bash
# Step 1: Start cleaning
curl -X POST http://localhost:8002/cleaning/start \
  -H "Content-Type: application/json" \
  -d '{"room_number":204,"housekeeper":"Maria"}'

# Step 2: Mark as clean
curl -X POST http://localhost:8002/cleaning/complete \
  -H "Content-Type: application/json" \
  -d '{"room_number":204}'
```

### TS-04 — Room 301 orders food
```bash
curl -X POST http://localhost:8003/orders \
  -H "Content-Type: application/json" \
  -d '{"room_number":201,"items":[{"name":"Coffee","quantity":2,"price":4.50},{"name":"Sandwich","quantity":1,"price":8.00}]}'
```

### TS-05 — Maintenance: Critical issue in Room 115
```bash
curl -X POST http://localhost:8004/requests \
  -H "Content-Type: application/json" \
  -d '{"room_number":105,"description":"Broken shower — water leaking","urgency":"Critical"}'
```

### TS-06 — Two simultaneous check-ins (same room type)
```bash
# Run both in parallel — system assigns different rooms
curl -X POST http://localhost:8001/checkin \
  -H "Content-Type: application/json" \
  -d '{"guest_name":"Alice Brown","room_type":"single","nights":2}' &

curl -X POST http://localhost:8001/checkin \
  -H "Content-Type: application/json" \
  -d '{"guest_name":"Bob Davis","room_type":"single","nights":1}'
```

### TS-07 — No rooms available (all occupied)
```bash
# After filling all single rooms, attempt another single check-in
curl -X POST http://localhost:8001/checkin \
  -H "Content-Type: application/json" \
  -d '{"guest_name":"Charlie Wilson","room_type":"single","nights":1}'
# Expected: 409 Conflict with "no_rooms_available" error
```

### TS-08 — Invalid room number
```bash
curl -X POST http://localhost:8001/checkout \
  -H "Content-Type: application/json" \
  -d '{"room_number":999,"early_checkout":false,"late_fee":0}'
# Expected: 404 Not Found with clear error message
```

---

## Project Structure

```
hotel_os/
│
├── shared/                     # Shared constants & event names
│   ├── config.py               # Ports, room inventory, status values
│   └── events.py               # Redis Pub/Sub channel names
│
├── broker/
│   └── broker.py               # Async Redis Pub/Sub wrapper (singleton)
│
├── reception_service/
│   ├── models.py               # Room, Guest dataclasses + Pydantic schemas
│   ├── algorithms.py           # Room Assignment Algorithm (7 steps)
│   ├── billing.py              # Billing Calculation Algorithm
│   └── main.py                 # FastAPI app — check-in, check-out, rooms
│
├── housekeeping_service/
│   ├── models.py               # CleaningTask dataclass
│   └── main.py                 # FastAPI app — cleaning queue, status updates
│
├── room_service/
│   ├── models.py               # Order, OrderItem dataclasses
│   └── main.py                 # FastAPI app — orders, state progression
│
├── maintenance_service/
│   ├── models.py               # MaintenanceRequest dataclass
│   └── main.py                 # FastAPI app — priority queue, technicians
│
├── dashboard/
│   ├── auth.py                 # HMAC token authentication
│   ├── main.py                 # FastAPI app — WebSocket + REST proxy
│   └── static/
│       ├── index.html          # Operations dashboard UI
│       ├── style.css           # Styling (Inter font, purple theme)
│       └── app.js              # WebSocket client + all interactions
│
├── requirements.txt
└── README.md
```

---

## Git Log

```
git log --oneline
```

---

## Technology Stack

| Component | Technology | Justification |
|---|---|---|
| Language | Python 3.11 | Async support, rich ecosystem, BTEC-friendly |
| Web Framework | FastAPI | Native async, auto Swagger docs, WebSocket built-in |
| Message Broker | Redis Pub/Sub | Lightweight, no separate broker server config needed |
| WebSocket | FastAPI WebSocket | Built-in, no extra library required |
| HTTP Client | httpx | Async HTTP for inter-service REST calls |
| Validation | Pydantic v2 | Type-safe request/response validation |
| Frontend | Vanilla JS + CSS | No build step, runs directly in browser |

---

## Security Notes

- Dashboard requires token authentication (HMAC-signed)
- All inputs validated via Pydantic before processing
- WebSocket connections require valid token in query param
- Errors are caught and returned as safe messages (no stack traces exposed)
- Guest payment details are never sent over WebSocket

---

*HotelOS — Built for BTEC Unit 4 Programming Assignment 2026*
