"""
RideWave Matching Engine Benchmark Script
-----------------------------------------
Reproducible standalone benchmark measuring latency and throughput for H3-based
nearby driver spatial lookups across varying driver densities (10, 50, 100, 500).

Usage:
    python backend/scripts/benchmark_matching.py [--dry-run] [--output results.json] [--iterations 100]
"""

import argparse
import asyncio
import json
import math
import os
import random
import statistics
import sys
import time
import uuid
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Driver, DriverStatus, User, UserRole
from app.services.location_cache import redis_store
from app.services.matcher import find_nearby_drivers
from app.services.spatial import coords_to_h3


class InMemoryRedisMock:
    """In-memory Redis store fallback when an external Redis server is not running."""

    def __init__(self):
        self.kv = {}
        self.sets = {}

    async def set(self, key: str, value: str, ex: int | None = None):
        self.kv[key] = value

    async def get(self, key: str) -> str | None:
        return self.kv.get(key)

    async def sadd(self, key: str, *members: str):
        if key not in self.sets:
            self.sets[key] = set()
        for m in members:
            self.sets[key].add(m)

    async def smembers(self, key: str) -> set:
        return self.sets.get(key, set()).copy()

    async def expire(self, key: str, ttl: int):
        pass

    async def ping(self):
        return True


async def check_or_setup_redis():
    """Verify if live Redis is available; fallback to InMemoryRedisMock if not."""
    try:
        client = await redis_store.get_client()
        await asyncio.wait_for(client.ping(), timeout=1.0)
        return "Live Redis (localhost:6379)"
    except Exception:
        redis_store._client = InMemoryRedisMock()
        return "InMemoryRedisMock (Standalone mode)"


def generate_jittered_coordinates(
    base_lat: float, base_lng: float, count: int, radius_km: float = 5.0
) -> list[tuple[float, float]]:
    """Generate uniformly scattered lat/lng coordinates within radius_km of base point."""
    coords = []
    # 1 deg lat ~= 111 km, 1 deg lng ~= 111 * cos(lat) km
    lat_degree_km = 111.0
    lng_degree_km = 111.0 * math.cos(math.radians(base_lat))

    for _ in range(count):
        # Random radius and angle
        r = radius_km * math.sqrt(random.random())
        theta = random.random() * 2 * math.pi
        d_lat = (r * math.cos(theta)) / lat_degree_km
        d_lng = (r * math.sin(theta)) / lng_degree_km
        coords.append((base_lat + d_lat, base_lng + d_lng))
    return coords


async def setup_benchmark_db():
    """Create isolated SQLite database for benchmark runs."""
    db_path = backend_dir / "benchmark_spatial.db"
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, session_factory, db_path


async def seed_drivers(
    session_factory,
    driver_coords: list[tuple[float, float]],
):
    """Seed database and Redis with driver records and ephemeral locations."""
    async with session_factory() as db:
        # Clear existing drivers and users
        await db.execute(delete(Driver))
        await db.execute(delete(User))
        await db.commit()

        if isinstance(redis_store._client, InMemoryRedisMock):
            redis_store._client.kv.clear()
            redis_store._client.sets.clear()

        for idx, (lat, lng) in enumerate(driver_coords):
            user = User(
                id=uuid.uuid4(),
                email=f"driver_{idx}_{uuid.uuid4().hex[:6]}@ridewave.io",
                hashed_password="bench_hash",
                full_name=f"Driver {idx}",
                role=UserRole.DRIVER,
            )
            db.add(user)
            await db.flush()

            driver = Driver(
                id=uuid.uuid4(),
                user_id=user.id,
                status=DriverStatus.ONLINE,
                vehicle_make="Toyota",
                vehicle_model="Prius",
                vehicle_plate=f"CAL-{idx:04d}",
                last_latitude=lat,
                last_longitude=lng,
            )
            db.add(driver)
            await db.flush()

            # Populate Redis ephemeral cache with H3 cell
            h3_cell = coords_to_h3(lat, lng)
            await redis_store.update_driver_location(
                driver_id=str(driver.id),
                latitude=lat,
                longitude=lng,
                h3_index=h3_cell,
                ttl_seconds=300,
            )

        await db.commit()


async def run_benchmark(
    densities: list[int],
    iterations: int,
    warmup: int,
    pickup_lat: float,
    pickup_lng: float,
    radius_km: float,
):
    """Execute benchmark across all specified driver densities."""
    redis_mode = await check_or_setup_redis()
    print(f"[*] Redis Engine: {redis_mode}")

    engine, session_factory, db_path = await setup_benchmark_db()
    print(f"[*] Benchmark DB: {db_path.name}")

    results = []

    try:
        for count in densities:
            print(f"\n--- Benchmarking Driver Density: {count} drivers ---")
            driver_coords = generate_jittered_coordinates(
                pickup_lat, pickup_lng, count, radius_km=6.0
            )
            await seed_drivers(session_factory, driver_coords)

            # Warmup iterations
            for _ in range(warmup):
                async with session_factory() as db:
                    _ = await find_nearby_drivers(pickup_lat, pickup_lng, radius_km, db)

            # Timed iterations
            latencies_ms = []
            start_wall = time.perf_counter()

            for _ in range(iterations):
                async with session_factory() as db:
                    t0 = time.perf_counter()
                    matched = await find_nearby_drivers(pickup_lat, pickup_lng, radius_km, db)
                    t1 = time.perf_counter()
                    latencies_ms.append((t1 - t0) * 1000.0)

            total_wall_time = time.perf_counter() - start_wall
            throughput = iterations / total_wall_time if total_wall_time > 0 else 0

            latencies_ms.sort()
            p50 = statistics.median(latencies_ms)
            p95 = latencies_ms[int(0.95 * len(latencies_ms))]
            p99 = latencies_ms[min(int(0.99 * len(latencies_ms)), len(latencies_ms) - 1)]
            mean_lat = statistics.mean(latencies_ms)

            metric = {
                "driver_count": count,
                "iterations": iterations,
                "p50_ms": round(p50, 3),
                "p95_ms": round(p95, 3),
                "p99_ms": round(p99, 3),
                "mean_ms": round(mean_lat, 3),
                "throughput_rps": round(throughput, 1),
                "sample_matched_count": len(matched),
            }
            results.append(metric)

            print(
                f"  Matched: {len(matched)}/{count} within {radius_km}km | "
                f"p50: {metric['p50_ms']}ms | p95: {metric['p95_ms']}ms | "
                f"p99: {metric['p99_ms']}ms | Throughput: {metric['throughput_rps']} req/s"
            )

    finally:
        await engine.dispose()
        if db_path.exists():
            try:
                db_path.unlink()
            except Exception:
                pass

    return results, redis_mode


def print_ascii_table(results: list[dict], redis_mode: str, hardware_info: dict):
    print("\n" + "=" * 78)
    print("           RideWave Spatial Matching Performance Benchmark Summary")
    print("=" * 78)
    print(f"Environment: Python {sys.version.split()[0]} on {sys.platform}")
    print(f"Storage:     {redis_mode} + SQLite / aiosqlite AsyncSession")
    print("-" * 78)
    header = (
        f"{'Drivers':<10} | {'Matched':<9} | {'p50 (ms)':<10} | "
        f"{'p95 (ms)':<10} | {'p99 (ms)':<10} | {'Req/Sec':<10}"
    )
    print(header)
    print("-" * 78)
    for r in results:
        row = (
            f"{r['driver_count']:<10} | {r['sample_matched_count']:<9} | "
            f"{r['p50_ms']:<10.3f} | {r['p95_ms']:<10.3f} | {r['p99_ms']:<10.3f} | "
            f"{r['throughput_rps']:<10.1f}"
        )
        print(row)
    print("=" * 78)


def main():
    parser = argparse.ArgumentParser(description="RideWave Matching Engine Benchmark")
    parser.add_argument("--dry-run", action="store_true", help="Run quick 2-iteration check")
    parser.add_argument("--iterations", type=int, default=100, help="Number of benchmark iterations")
    parser.add_argument("--warmup", type=int, default=10, help="Number of warmup iterations")
    parser.add_argument("--lat", type=float, default=37.7749, help="Pickup latitude (San Francisco)")
    parser.add_argument("--lng", type=float, default=-122.4194, help="Pickup longitude (San Francisco)")
    parser.add_argument("--radius", type=float, default=5.0, help="Search radius in km")
    parser.add_argument("--output", type=str, default=None, help="Output path for JSON results")
    args = parser.parse_args()

    densities = [10, 50, 100, 500]
    iterations = 2 if args.dry_run else args.iterations
    warmup = 1 if args.dry_run else args.warmup

    print("==================================================================")
    print("           RideWave Driver Matching Engine Benchmark              ")
    print("==================================================================")
    print(f"Densities:    {densities}")
    print(f"Iterations:   {iterations} (Warmup: {warmup})")
    print(f"Origin Coords: ({args.lat}, {args.lng}) | Search Radius: {args.radius} km")

    results, redis_mode = asyncio.run(
        run_benchmark(
            densities=densities,
            iterations=iterations,
            warmup=warmup,
            pickup_lat=args.lat,
            pickup_lng=args.lng,
            radius_km=args.radius,
        )
    )

    print_ascii_table(results, redis_mode, {})

    if args.output:
        out_path = Path(args.output)
        out_payload = {
            "metadata": {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
                "python_version": sys.version,
                "platform": sys.platform,
                "redis_mode": redis_mode,
                "pickup_coords": [args.lat, args.lng],
                "search_radius_km": args.radius,
                "iterations_per_density": iterations,
            },
            "results": results,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out_payload, f, indent=2)
        print(f"[+] Results saved to {out_path.resolve()}")


if __name__ == "__main__":
    main()
