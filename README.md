# RideWave — High-Concurrency Ride-Hailing Platform

[![Next.js](https://img.shields.io/badge/Next.js-16.4-black?style=flat&logo=next.js)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat&logo=postgresql)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat&logo=redis)](https://redis.io/)
[![Uber H3](https://img.shields.io/badge/Spatial-Uber%20H3%20v4-blue)](https://h3geo.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**RideWave** is a production-grade, distributed ride-hailing system inspired by modern mobility platforms such as Uber. It demonstrates advanced backend architecture: **concurrency-safe driver assignment**, **two-tiered spatial indexing**, **ephemeral GPS ingestion over WebSockets**, a **Transactional Outbox event pipeline**, and a **zero-cost sandboxed AI Trip Assistant**.

---

## 🌐 Live Deployments

- **Frontend (Vercel):** [https://ridewave-rosy.vercel.app](https://ridewave-rosy.vercel.app)
- **Backend API (Render):** [https://ridewave-backend-k97z.onrender.com](https://ridewave-backend-k97z.onrender.com)
- **Interactive OpenAPI / Swagger Docs:** [https://ridewave-backend-k97z.onrender.com/api/v1/docs](https://ridewave-backend-k97z.onrender.com/api/v1/docs)

---

## 🏗️ System Architecture

RideWave is built as a **modular monolith** with clean bounded contexts, ensuring high operational velocity without premature distributed transaction overhead.

```
┌───────────────────────────────────────────────────────────────────────────┐
│                             Next.js 16 Frontend                           │
│   (Rider UI / Driver Terminal / Leaflet + OpenStreetMap / WSS Tracking)   │
└─────────────────────────────────────┬─────────────────────────────────────┘
                                      │ HTTPS / WSS
                                      ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                          FastAPI Modular Monolith                         │
│                                                                           │
│   [/auth]       [/rides]       [/drivers]       [/matching]  [/assistant] │
│      │             │               │                 │            │       │
│      └─────────────┴───────┬───────┴                 │            │       │
│                            ▼                         ▼            ▼       │
│                     Domain Services           Spatial Engine  LLM Adapter │
│                    (Ride Lifecycle)           (Uber H3 Grid)  (OpenRouter)│
└────────────────────────────┬─────────────────────────┬────────────┬───────┘
                             │                         │            │
             ┌───────────────┴───────────────┐         │            │
             ▼                               ▼         ▼            ▼
 ┌──────────────────────┐        ┌───────────────────────┐  ┌───────────────┐
 │ PostgreSQL Database  │        │  Redis Ephemeral Store│  │  External Free│
 │ - Durable Trips      │        │  - High-Freq GPS TTL  │  │   LLM Service │
 │ - Partial Unique Idx │        │  - H3 Cell Buckets    │  │ (Llama 3.2 3B)│
 │ - Transaction Outbox │        │  - WebSocket Pub/Sub  │  └───────────────┘
 └───────────┬──────────┘        └───────────────────────┘
             │
             │ Outbox Poller / CDC
             ▼
 ┌──────────────────────┐
 │ Apache Kafka Brokers │
 │ - ride.requested     │
 │ - ride.accepted      │
 │ - ride.completed     │
 └──────────────────────┘
```

---

## ⚡ Core Technical Features & Engineering Highlights

### 1. Two-Tiered Spatial Driver Discovery
- **Tier 1 (Coarse Indexing via Uber H3 v4):** Converts geographic coordinates to discrete hexagonal global grid cells (`res=8`) and queries neighboring candidate rings (`grid_disk`) directly from Redis sets in $O(1)$ time.
- **Tier 2 (Precise Filtering & Distance Ranking):** Evaluates candidate freshness and performs spherical Haversine distance computations to rank drivers by straight-line proximity before attempting assignment.

### 2. High-Concurrency Driver Assignment Safety
- Eliminates the classic distributed race condition where two riders match with the same available driver simultaneously.
- Protected by a **PostgreSQL Partial Unique Constraint Index**:
  ```sql
  CREATE UNIQUE INDEX idx_driver_single_active_ride ON rides (driver_id)
  WHERE status IN ('ACCEPTED', 'ARRIVED', 'IN_PROGRESS');
  ```
- Combined with atomic in-transaction locking (`SELECT ... FOR UPDATE`), ensuring strict database-level serializability under high concurrency.

### 3. Dual Storage Separation (Durable vs. Ephemeral)
- **High-Frequency GPS Ingestion (1–3 Hz):** Streamed over authenticated WebSockets directly into Redis with rolling 30-second TTLs.
- **Durable Business Records:** Only trip milestone states (`REQUESTED`, `ACCEPTED`, `ARRIVED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`) write to PostgreSQL, avoiding database IOPS exhaustion.

### 4. Transactional Outbox Pattern for Event Streaming
- Avoids dual-write inconsistencies between the database and event brokers (Apache Kafka).
- State transitions and corresponding domain events (`ride.requested`, `ride.accepted`, `ride.completed`) are committed in the **same atomic database transaction** into the `outbox_events` table before asynchronous publication.

### 5. Sandboxed Zero-Cost AI Trip Assistant
- Leverages free-tier inference (`meta-llama/llama-3.2-3b-instruct:free` via OpenRouter or local Ollama).
- **Security Invariant:** All LLM tool-calling functions are read-only and explicitly bound to the authenticated session's `user_id`. The LLM cannot access arbitrary database records, invent fares, or mutate ride states.

---

## 📊 Data Model & Ride State Machine

### Finite State Machine
```
  [REQUESTED] ──► [MATCHING] ──► [ACCEPTED] ──► [ARRIVED] ──► [IN_PROGRESS] ──► [COMPLETED]
       │              │               │             │
       ▼              ▼               ▼             ▼
  [CANCELLED]    [CANCELLED]     [CANCELLED]   [CANCELLED]
```

### Relational Schema (PostgreSQL)
- **`users`**: ID, email, hashed password (bcrypt), role (`RIDER`, `DRIVER`, `ADMIN`), timestamps.
- **`drivers`**: ID, user reference, status (`OFFLINE`, `ONLINE`, `BUSY`), vehicle make/model/plate, last known coordinates.
- **`rides`**: ID, rider reference, driver reference (nullable until matched), status, pickup/dropoff coordinates & addresses, estimated fare, final fare, currency, timestamps.
- **`ride_events`**: Immutable audit log of every lifecycle state transition.
- **`idempotency_keys`**: Idempotent ride creation cache preventing duplicate booking requests.
- **`outbox_events`**: Transactional outbox buffer for asynchronous event dispatch.

---

## 🛠️ Tech Stack

| Layer | Technologies Used |
|---|---|
| **Frontend** | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS, Lucide Icons |
| **Maps & Geospatial** | Leaflet, React-Leaflet, OpenStreetMap, Uber H3 (v4 Python SDK) |
| **Backend API** | Python 3.11, FastAPI, Uvicorn, Pydantic v2 |
| **Database & ORM** | PostgreSQL 16 / SQLite (local dev), SQLAlchemy 2.0 (Async), Alembic |
| **Caching & Real-Time** | Redis 7, FastAPI WebSockets, Starlette CORS |
| **Testing & Quality** | pytest, pytest-asyncio, HTTPX, Ruff (Linter & Formatter) |
| **Containers & CI/CD** | Docker (Multi-stage), Docker Compose, GitHub Actions |

---

## 🚀 Getting Started Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/ThayanithiR/ridewave.git
cd ridewave
```

### 2. Backend Setup
```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1    # On Linux/macOS: source venv/bin/activate
pip install -e . -e ".[dev]" aiosqlite "pydantic[email]" "sqlalchemy[asyncio]" greenlet
```

Run database initialization and start the FastAPI server:
```bash
python init_db.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- API will be accessible at: `http://127.0.0.1:8000`
- Swagger UI will be accessible at: `http://127.0.0.1:8000/api/v1/docs`

### 3. Frontend Setup
In a new terminal window:
```bash
cd frontend
npm install
npm run dev
```
Open **`http://localhost:3000`** in your browser.

---

## 🧪 Running the Test Suite

The test suite covers unit logic, pricing algorithms, lifecycle transitions, spatial neighborhood indexing, and concurrency safety:

```bash
cd backend
pytest -v
```

**Test Coverage Highlights:**
- `tests/test_pricing.py`: Great-circle Haversine distance and deterministic fare calculations.
- `tests/test_lifecycle.py`: End-to-end trip creation, driver assignment, arrival, start, completion, and cancellation.
- `tests/test_spatial_concurrency.py`: Uber H3 7-cell neighborhood validation, route interpolation, and race condition prevention asserting that a busy driver cannot be booked by concurrent riders.
- `tests/test_events_and_assistant.py`: Transactional outbox persistence and AI tool session isolation.

---

## 🔒 Security & Reliability Practices

- **Zero Plaintext Credentials:** Passwords hashed with salted bcrypt (72-byte ceiling).
- **Session Authentication:** Short-lived JWT Bearer access tokens with role-based dependencies (`RIDER`, `DRIVER`, `ADMIN`).
- **Idempotency Safeguards:** Ride creation endpoints accept an `idempotency_key` preventing duplicate charges or trips from network retries.
- **Fail-Safe Caching:** Redis connection outages degrade gracefully without crashing core trip lifecycle operations.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
