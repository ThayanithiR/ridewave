# RideWave — Architecture & System Design Document

## 1. System Overview
RideWave is a high-concurrency, production-style ride-hailing backend and web application. It models core real-time mobility systems:
- **Two-Tiered Spatial Discovery:** H3 hexagonal indexing (Resolution 8) in Redis combined with database candidate filtering and Haversine ranking.
- **Concurrency-Safe Driver Assignment:** Row-level locking (`with_for_update()`) and PostgreSQL partial unique indexing (`idx_driver_single_active_ride`) preventing double-booking under simultaneous race conditions.
- **Strict State Machine:** Explicit transitions validated in Python domain services, recording transition timestamps.
- **Durable Event Audit (Transactional Outbox):** Atomic write of domain events (`RIDE_REQUESTED`, `DRIVER_ASSIGNED`, etc.) in the exact same transaction as the ride state change, guaranteeing at-least-once event persistence without dual-write race conditions.
- **Zero-Cost, Safe AI Assistant:** Local Ollama (`llama3.2:3b`) or OpenRouter free models operating strictly as read-only helpers with deterministic fallbacks, kept completely off the critical ride booking path.

```
+-----------------------------------------------------------------------------------+
|                                 Next.js Frontend                                  |
|   (Rider UI / Driver UI / Leaflet + OpenStreetMap / WebSocket Client / AI Chat)   |
+------------------------------------------+----------------------------------------+
                                           | HTTPS / WSS
                                           v
+-----------------------------------------------------------------------------------+
|                            FastAPI Modular Monolith                               |
|                                                                                   |
|  [/auth]       [/rides]       [/drivers]       [/matching]       [/assistant]     |
|     |             |               |                 |                 |           |
|     +-------------+-------+-------+                 |                 |           |
|                           |                         |                 |           |
|                           v                         v                 v           |
|                   Domain Services           Spatial Engine       LLM Adapter      |
|                   (Ride Lifecycle)         (H3 / PostGIS)       (Local Ollama)    |
+---------------------------+-------------------------+-----------------+-----------+
                            |                         |                 |
            +---------------+---------------+         |                 |
            |                               |         |                 |
            v                               v         v                 |
+------------------------+      +-------------------------+             |
| PostgreSQL + PostGIS   |      | Redis Cache & Pub/Sub   |             |
| - Durable state        |      | - Ephemeral driver GPS  |             |
| - Transactional Outbox |      | - WS Fanout channels    |             |
| - Partial Unique Index |      | - Rate limiting         |             |
+-----------+------------+      +-------------------------+             |
            |                                                           |
            | Outbox Event Log                                          v
            | (Durable audit implemented;                      +------------------------+
            |  Kafka broker publisher: planned future work)    | Local Ollama / Free    |
            v                                                  | Hosted Inference       |
+------------------------+                                     +------------------------+
| Outbox Consumer /      |
| Planned Kafka Broker   |
+------------------------+
```

---

## 2. Key Architectural Decisions (ADRs)

### ADR-01: Modular Monolith Architecture
- **Decision:** Build as a single, cohesive FastAPI codebase with explicit domain modules (`auth`, `users`, `drivers`, `rides`, `matching`, `events`, `assistant`).
- **Rationale:** Minimizes network latency, eliminates distributed transaction overhead (no two-phase commits across microservices), and allows simpler schema management while maintaining strict domain boundaries.

### ADR-02: Concurrency-Safe Driver Assignment
- **Problem:** Multiple riders could match or confirm the same available driver simultaneously, causing double-assignment anomalies.
- **Solution:** 
  1. **Partial Unique Index:**
     ```sql
     CREATE UNIQUE INDEX idx_driver_single_active_ride ON rides (driver_id)
     WHERE status IN ('ACCEPTED', 'ARRIVED', 'IN_PROGRESS');
     ```
  2. **Row-Level Lock:** `SELECT ... FOR UPDATE` acquires an exclusive lock on the driver row inside the transaction.
  3. **Atomic State Transition:** Driver status is updated to `BUSY`. If a race condition bypasses application logic, the database engine enforces the partial unique constraint, raising an `IntegrityError` which returns an HTTP 409 Conflict.

### ADR-03: Two-Tiered Spatial Search
- **Tier 1 (Candidate Retrieval):** Uber H3 hexagonal discrete global grid (Resolution 8). Driver IDs in the pickup cell and 2 concentric neighbor rings (19 cells) are indexed in memory/Redis set buckets.
- **Tier 2 (Precise Filtering & Ranking):** The database filters active, online drivers by ID and computes exact spherical Haversine distances to return candidates strictly ordered by proximity.

### ADR-04: Separation of Ephemeral GPS and Durable Trips
- High-frequency GPS telemetry (1–3 Hz) travels over authenticated WebSockets directly into Redis with an auto-expiring TTL (60s).
- PostgreSQL only persists durable trip milestones (`REQUESTED`, `ACCEPTED`, `ARRIVED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`), shielding the primary relational database from telemetry IOPS exhaustion.

### ADR-05: Transactional Outbox Pattern (Path B)
- **Status:** **Implemented** in `outbox_events` table. Every ride lifecycle event (`RIDE_REQUESTED`, `DRIVER_ASSIGNED`, etc.) is written within the exact same database transaction as the ride state mutation.
- **Future Scope:** External Kafka broker pub/sub publishing and consumer streaming is planned work. The outbox log serves as a durable, reliable event ledger ready for downstream CDC (Change Data Capture) or Kafka worker publishing.

### ADR-06: Zero-Cost, Safe AI Trip Assistant
- **Decision:** Local Ollama (`llama3.2:3b`) with optional free OpenRouter hosted fallback. Kept strictly read-only and off the critical booking/payment path.
- **Rationale:** Zero API credit barrier for local development, reproducible portfolio demonstration, and defensive architecture (trip booking works even if LLM service is offline).
