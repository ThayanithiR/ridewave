# RideWave — Architecture & System Design Document

## 1. System Overview
RideWave is a high-concurrency, production-style ride-hailing backend and web application. It models core real-time mobility systems:
- Spatial driver discovery and candidate ranking.
- Concurrency-safe, atomic driver matching.
- Asynchronous high-frequency GPS ingestion and WebSocket fan-out.
- Asynchronous event delivery with idempotency and transactional outbox.
- Secure, read-only AI Trip Assistant using OpenRouter's free-tier open models.

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
|                   (Ride Lifecycle)         (H3 / PostGIS)       (OpenRouter Free) |
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
            | Outbox poller / CDC                                       |
            v                                                           v
+------------------------+                                 +------------------------+
| Apache Kafka (Events)  |                                 | External Free LLM API  |
| - ride.requested       |                                 | (OpenRouter Free Tier) |
| - ride.assigned        |                                 +------------------------+
| - ride.completed       |
+------------------------+
```

---

## 2. Key Architectural Decisions (ADRs)

### ADR-01: Modular Monolith vs Microservices
- **Decision:** Start as a single FastAPI codebase with explicit domain modules (`auth`, `users`, `drivers`, `rides`, `matching`, `events`, `assistant`).
- **Rationale:** Avoid premature network latency, distributed transactions, and operational complexity. Decouple by domain interfaces, allowing individual services to be extracted later if necessary.

### ADR-02: Driver Assignment Concurrency Safety
- **Problem:** Two riders could concurrently request or match the same available driver.
- **Decision:** 
  1. PostgreSQL Partial Unique Index:
     ```sql
     CREATE UNIQUE INDEX idx_driver_single_active_ride ON rides (driver_id)
     WHERE status IN ('ACCEPTED', 'ARRIVED', 'IN_PROGRESS');
     ```
  2. In-transaction conditional state transition:
     ```sql
     UPDATE drivers SET status = 'BUSY' WHERE id = :driver_id AND status = 'ONLINE';
     ```
  3. Combine with `SELECT ... FOR UPDATE` on candidate assignment.

### ADR-03: Two-Tiered Spatial Search
- **Tier 1 (Candidate Retrieval):** Uber H3 hexagonal discrete global grid (resolution 8/9). Retrieve driver IDs in the pickup cell and k-ring neighboring cells from memory/Redis.
- **Tier 2 (Precise Filtering & Ranking):** PostGIS `ST_Distance` spherical calculations to sort candidates by straight-line distance, eligibility, and freshness.

### ADR-04: Separation of Ephemeral GPS and Durable Trips
- High-frequency GPS updates (1–3 Hz) are routed through authenticated WebSockets and held in Redis with short TTLs (30s).
- PostgreSQL only records milestone coordinates (`PICKUP`, `DROPOFF`) and completed trip summaries, preserving database IOPS.

### ADR-05: Transactional Outbox for Kafka Events
- Status changes and outgoing domain events are written in the *same* database transaction to `rides` and `outbox_events`.
- A background publisher tails `outbox_events` and emits to Kafka topics, ensuring at-least-once delivery without distributed dual-write inconsistencies.

### ADR-06: Zero-Cost LLM Tool Integration
- AI Trip Assistant uses OpenRouter free tier (models like `meta-llama/llama-3.2-3b-instruct:free` or `qwen/qwen-2.5-7b-instruct:free`).
- Read-only tools bound strictly to the authenticated user's session token. LLM never calculates authoritative fares or performs state mutations.
