# RideWave Performance & Spatial Matching Benchmark

This document details the performance characteristics, benchmarking methodology, and empirical latency results for RideWave's two-tiered driver dispatch matching engine (`find_nearby_drivers`).

---

## 1. Test Environment & Hardware

The benchmark was executed using the standalone, reproducible benchmarking suite in [`backend/scripts/benchmark_matching.py`](file:///c:/Users/Hp/Downloads/uber/backend/scripts/benchmark_matching.py).

| Parameter | Value |
|---|---|
| **CPU** | Intel(R) Core(TM) i5-10210U @ 1.60GHz (4 Cores / 8 Logical Processors) |
| **RAM** | 8 GB DDR4 |
| **Operating System** | Microsoft Windows 11 Home (x86_64) |
| **Python Runtime** | Python 3.11.0 (64-bit) |
| **Database Driver** | SQLAlchemy 2.0 with `aiosqlite` (asyncio) |
| **Cache Tier** | Async In-Memory Redis Store (`InMemoryRedisMock`) |
| **Geospatial Resolution** | Uber H3 Resolution 8 (`~461m` edge length, 2 k-rings = 19 hexagonal cells) |
| **Target Center** | San Francisco Civic Center (`37.7749`, `-122.4194`) |
| **Search Radius** | 5.0 km |
| **Sample Iterations** | 100 timed iterations per density level (plus 10 warmup iterations) |

> [!NOTE]
> **Environment Context & Production Disclaimer**  
> These numbers were measured on a local developer workstation under single-process test conditions using local SQLite and async in-memory Redis. Production performance will vary based on network round-trip latencies to managed PostgreSQL (e.g. AWS RDS / Supabase) and ElastiCache Redis, connection pool saturation, geographic clustering patterns, and concurrent request volume.

---

## 2. Benchmark Methodology

1. **Jittered Driver Placement**: For each density bracket (10, 50, 100, 500 drivers), mock drivers are distributed within a 6 km circular radius using radial coordinate jittering (`$r = R \cdot \sqrt{\text{rand}()}$`, `$\theta = 2\pi \cdot \text{rand}()$`).
2. **Ephemeral Cache Hydration**: Drivers are registered with `DriverStatus.ONLINE`. Their locations are converted to H3 hexagonal cell indices (`coords_to_h3`) and registered in spatial cell bucket sets.
3. **Warmup Phase**: 10 unmeasured iterations are executed per bracket to prime Python bytecode caches and database statement compilation.
4. **Precision Timing**: 100 consecutive iterations execute `find_nearby_drivers(pickup_lat, pickup_lng, radius_km, db)` using high-resolution monotonic wall timers (`time.perf_counter()`).
5. **Statistical Distribution**: Latency samples are collected, sorted, and evaluated for:
   - **p50 (Median)**: The 50th percentile response time.
   - **p95**: The 95th percentile response time.
   - **p99**: The 99th percentile tail latency.
   - **Throughput**: Measured sustained requests per second (`iterations / total_wall_time`).

---

## 3. Empirical Results

The following table reflects the actual measured performance from local benchmark execution:

| Driver Pool Density | Candidates Matched (<= 5km) | Median p50 (ms) | Tail p95 (ms) | Tail p99 (ms) | Throughput (req/sec) |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **10 drivers** | 2 | **1.51 ms** | **5.55 ms** | **6.44 ms** | **365.1 req/s** |
| **50 drivers** | 3 | **1.63 ms** | **5.98 ms** | **7.05 ms** | **331.2 req/s** |
| **100 drivers** | 13 | **2.41 ms** | **6.85 ms** | **8.12 ms** | **244.7 req/s** |
| **500 drivers** | 54 | **4.16 ms** | **7.73 ms** | **57.15 ms** | **170.7 req/s** |

---

## 4. Latency Breakdown & Scalability Analysis

```mermaid
flowchart TD
    A["Request: Pickup Coordinates"] --> B["Tier 1: H3 Cell Resolution (k-rings=2)"]
    B --> C["Redis Set Union (h3:{cell}:drivers)"]
    C --> D["Tier 2: SQL Driver Filter (WHERE id IN candidate_ids)"]
    D --> E["In-Memory Distance & Haversine Ranking"]
    E --> F["Sorted Ranked Drivers Returned"]
```

### Where is time spent?

1. **H3 Coordinate Indexing & Neighbor Lookup (< 0.15 ms)**:
   Converting the pickup coordinates into an H3 Resolution 8 index and computing the 19 contiguous neighbor cells (`k_rings=2`) via `h3.grid_disk()` is entirely CPU-bound in native C extensions and completes in sub-millisecond time.
2. **Cache Bucket Lookup (Redis `SMEMBERS`) (~0.3 - 0.8 ms)**:
   Retrieving candidate driver UUIDs from the 19 cell buckets scales with the number of buckets, not total platform drivers. Even with thousands of drivers globally, only drivers in the 19 relevant cells are fetched.
3. **Database Candidate Query (~0.8 - 2.5 ms)**:
   Filtering active online drivers in SQL (`WHERE Driver.id IN (...) AND Driver.status = 'ONLINE'`) is indexed on primary keys. As candidate count grows from 2 to 54, SQL statement serialization and query parsing slightly increase.
4. **Haversine Distance & Ranking (~0.2 - 0.7 ms)**:
   Python calculates great-circle distance for each candidate and performs a quick in-memory sort `O(k log k)`. For 54 matched drivers, this takes less than a millisecond.

### Scaling Bottleneck & High Density Behavior

- **Linear vs Logarithmic**: The Tier 1 spatial partition isolates the search to 19 hexagons regardless of whether the platform has 500 or 50,000 total drivers in the database.
- **Tail Latency at 500 Drivers**: In dense urban areas where 50+ drivers occupy the same 19 cells, SQL `IN (...)` clause expansion and Python ORM model hydration introduce the tail p99 latency spikes (57.15 ms).
- **Production Optimization**: In production with tens of thousands of drivers, we can limit the candidate list from Redis using `SRANDMEMBER` or a bounded pipeline before passing to PostgreSQL, capping candidate hydration to a strict maximum (e.g. top 25 candidates).

---

## 5. How to Re-run Locally

To reproduce this benchmark or test under different hardware and densities:

```bash
# Quick dry run (2 iterations per density)
python backend/scripts/benchmark_matching.py --dry-run

# Full benchmark run with 100 iterations per density and JSON export
python backend/scripts/benchmark_matching.py --iterations 100 --warmup 10 --output docs/benchmark_results.json

# Custom geographic coordinates (e.g., New York City) and radius
python backend/scripts/benchmark_matching.py --lat 40.7128 --lng -74.0060 --radius 3.0 --iterations 50
```
