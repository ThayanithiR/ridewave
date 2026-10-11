# RideWave — Entity-Relationship (ER) Data Model

## 1. Relational Entities (PostgreSQL)

```mermaid
erDiagram
    USERS ||--o| DRIVERS : "is a"
    USERS ||--o{ RIDES : "requests as rider"
    DRIVERS ||--o{ RIDES : "executes as driver"
    RIDES ||--o{ RIDE_EVENTS : "records"
    RIDES ||--o{ FARE_QUOTES : "originates from"
    USERS ||--o{ IDEMPOTENCY_KEYS : "owns"

    USERS {
        uuid id PK
        string email UK
        string hashed_password
        string full_name
        string role "RIDER | DRIVER | ADMIN"
        timestamp created_at
        timestamp updated_at
    }

    DRIVERS {
        uuid id PK
        uuid user_id FK, UK
        string status "OFFLINE | ONLINE | BUSY"
        string vehicle_make
        string vehicle_model
        string vehicle_plate
        geometry last_known_location "POINT(lon, lat)"
        timestamp last_location_at
        timestamp created_at
        timestamp updated_at
    }

    RIDES {
        uuid id PK
        uuid rider_id FK
        uuid driver_id FK "nullable until matched"
        string status "REQUESTED | MATCHING | ACCEPTED | ARRIVED | IN_PROGRESS | COMPLETED | CANCELLED"
        geometry pickup_location "POINT(lon, lat)"
        string pickup_address
        geometry dropoff_location "POINT(lon, lat)"
        string dropoff_address
        decimal estimated_fare
        decimal final_fare "nullable until complete"
        string currency
        timestamp requested_at
        timestamp accepted_at
        timestamp picked_up_at
        timestamp completed_at
        timestamp cancelled_at
        string cancellation_reason
    }

    RIDE_EVENTS {
        uuid id PK
        uuid ride_id FK
        string event_type
        string actor_role "RIDER | DRIVER | SYSTEM"
        uuid actor_id
        jsonb metadata
        timestamp created_at
    }

    FARE_QUOTES {
        uuid id PK
        uuid rider_id FK
        geometry pickup_location
        geometry dropoff_location
        decimal distance_km
        decimal estimated_duration_mins
        decimal base_fare
        decimal distance_fare
        decimal time_fare
        decimal total_fare
        string currency
        timestamp expires_at
        timestamp created_at
    }

    IDEMPOTENCY_KEYS {
        uuid id PK
        uuid user_id FK
        string idempotency_key UK
        string request_path
        jsonb response_payload
        integer response_status_code
        timestamp expires_at
        timestamp created_at
    }

    OUTBOX_EVENTS {
        uuid id PK
        string aggregate_type "RIDE | DRIVER | USER"
        uuid aggregate_id
        string event_type
        jsonb payload
        string status "PENDING | PUBLISHED | FAILED"
        integer retry_count
        timestamp created_at
        timestamp published_at
    }
```

---

## 2. Invariants & Database Constraints

1. **Active Ride Uniqueness per Driver:**
   ```sql
   CREATE UNIQUE INDEX idx_driver_single_active_ride ON rides (driver_id)
   WHERE status IN ('ACCEPTED', 'ARRIVED', 'IN_PROGRESS');
   ```
2. **Spatial Indexes:**
   ```sql
   CREATE INDEX idx_rides_pickup_location ON rides USING GIST (pickup_location);
   CREATE INDEX idx_rides_dropoff_location ON rides USING GIST (dropoff_location);
   CREATE INDEX idx_drivers_last_location ON drivers USING GIST (last_known_location);
   ```
3. **Idempotency Protection:**
   ```sql
   CREATE UNIQUE INDEX idx_user_idempotency_key ON idempotency_keys (user_id, idempotency_key);
   ```
4. **Time & Audit Consistency:**
   All timestamps stored in UTC (`TIMESTAMPTZ`).
