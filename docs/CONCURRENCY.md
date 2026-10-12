# Concurrency Control & Race Condition Mitigation in RideWave

## 1. Problem Statement

In on-demand ride-hailing systems, the **driver assignment phase** presents a classic distributed race condition:
- Two or more riders simultaneously select or match with the exact same available driver.
- Two API workers concurrently process requests to `POST /api/v1/rides/{ride_id}/accept` for the same driver.
- Without database-level isolation, an application-level "check-then-write" race can lead to double-booking, where the same driver is assigned to two concurrent active trips (`ACCEPTED`, `ARRIVED`, or `IN_PROGRESS`).

---

## 2. Multi-Layered Defense-in-Depth Strategy

RideWave employs a strict multi-layered locking and database constraint architecture to guarantee that no driver can ever hold more than one active trip simultaneously.

```
Incoming Concurrent Requests (Ride 1, Ride 2)
              │
              ▼
 Layer 1: Row-Level Locking (`SELECT ... FOR UPDATE`)
          - Serializes access to Driver record by user_id
          - Serializes access to Ride record by ride_id
              │
              ▼
 Layer 2: State Machine Validation (`validate_and_apply_transition`)
          - Asserts driver.status == ONLINE
          - Asserts ride.status in [REQUESTED, MATCHING] -> transitions to ACCEPTED
              │
              ▼
 Layer 3: Database Partial Unique Index (`idx_driver_single_active_ride`)
          - CREATE UNIQUE INDEX ON rides (driver_id)
            WHERE status IN ('ACCEPTED', 'ARRIVED', 'IN_PROGRESS');
          - Hard database constraint preventing double assignment even across multiple processes
              │
              ▼
 Layer 4: Transaction Rollback & Deterministic Conflict Handling
          - Winner receives HTTP 200 OK
          - Competing transaction catches IntegrityError, rolls back, returns HTTP 409 Conflict
```

### Layer 1: Row-Level Locking (`SELECT ... FOR UPDATE`)
When an assignment request arrives, the transaction locks both the driver and the targeted ride rows:
```python
driver_stmt = select(Driver).where(Driver.user_id == current_user.id).with_for_update()
driver = (await db.execute(driver_stmt)).scalar_one_or_none()

ride_stmt = select(Ride).where(Ride.id == ride_id).with_for_update()
ride = (await db.execute(ride_stmt)).scalar_one_or_none()
```
This forces concurrent transactions attempting to modify the same driver or ride to queue sequentially rather than interleaving dirty reads.

### Layer 2: Domain State Machine Enforcement
Before assignment occurs, the domain state machine strictly validates that:
1. `driver.status == DriverStatus.ONLINE`: If another transaction already committed `driver.status = BUSY`, the competing request fails fast with `409 Conflict`.
2. `ride.status` is valid for transitioning to `ACCEPTED`.

### Layer 3: Database Partial Unique Constraint
Even in distributed deployments with connection pools or multi-node clusters, the database remains the ultimate source of truth via a PostgreSQL Partial Unique Index:
```sql
CREATE UNIQUE INDEX idx_driver_single_active_ride ON rides (driver_id)
WHERE status IN ('ACCEPTED', 'ARRIVED', 'IN_PROGRESS');
```
*(Also configured with `sqlite_where` in SQLAlchemy metadata to enforce identical constraint semantics during local development and testing).*

If two transactions slip past application-level checks, the unique index rejects the second `INSERT`/`UPDATE` at the database engine level with an `IntegrityError`.

### Layer 4: Deterministic HTTP 409 Conflict Response
In the event of an `IntegrityError`, the transaction is rolled back immediately, and the client receives a well-defined response:
```json
{
  "detail": "Driver already assigned to an active ride or concurrent assignment conflict."
}
```

---

## 3. Concurrency Test Verification

The test `tests/test_spatial_concurrency.py::test_concurrent_driver_assignment_safety` proves this behavior through actual simultaneous execution:
1. Two distinct riders register and create separate rides (`ride1` and `ride2`).
2. A driver registers and goes `ONLINE`.
3. Two requests to `POST /api/v1/rides/{ride_id}/accept` are dispatched simultaneously using `asyncio.gather(task1, task2)` across separate database sessions.
4. The test verifies:
   - Status codes are strictly `[200, 409]`: Exactly one winner and one conflict.
   - Driver profile status in the database is `BUSY`.
   - Direct database query confirms the driver has **exactly 1 active ride** (`len(active_rides) == 1`).

---

## 4. Trade-Offs & Architectural Considerations

| Approach | Trade-Offs | RideWave Decision |
|---|---|---|
| **Optimistic Locking (Version column)** | Fast for read-heavy workloads, but high retry overhead and aborted transactions under high contention. | Rejected for assignment path; used for high-frequency GPS cache instead. |
| **Pessimistic Locking (`SELECT FOR UPDATE`)** | Holds row lock for transaction duration; potential deadlocks if locks acquired out of order. | Selected. Deadlocks prevented by acquiring locks in deterministic order: Driver first, then Ride. |
| **Redis Distributed Lock (Redlock)** | Fast in-memory locking across nodes, but vulnerable to clock drift, network partitions, and dual-write inconsistencies. | Used only as cache; PostgreSQL remains authoritative. |
| **Partial Unique Index** | Modest index maintenance cost on status change. | Essential safety net. Guarantees zero duplicate active rides even if application logic has bugs. |
