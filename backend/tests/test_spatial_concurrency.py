import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.services.simulator import interpolate_route
from app.services.spatial import coords_to_h3, get_search_cells

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(
    TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="function")
def anyio_backend():
    return "asyncio"


def test_h3_spatial_indexing():
    lat, lng = 40.7580, -73.9855  # Times Square
    cell = coords_to_h3(lat, lng, resolution=8)
    assert cell is not None
    assert len(cell) > 5

    search_cells = get_search_cells(lat, lng, k_rings=1, resolution=8)
    # k-ring 1 around a hexagon always contains exactly 7 cells (1 center + 6 neighbors)
    assert len(search_cells) == 7
    assert cell in search_cells


def test_driver_route_interpolation():
    start = (40.7128, -74.0060)
    end = (40.7589, -73.9851)
    points = list(interpolate_route(start, end, steps=5))
    assert len(points) == 6
    assert points[0] == start
    assert points[-1] == end


import asyncio
import os
import uuid
from sqlalchemy import select
from app.models import Driver, Ride, RideStatus


@pytest.mark.asyncio
async def test_concurrent_driver_assignment_safety():
    """
    True Concurrency Test:
    Simultaneously dispatches two overlapping accept requests for the exact same driver
    across two distinct rides using asyncio.gather().
    Uses separate database connections/sessions to guarantee true multi-connection race conditions.
    Asserts that:
      1. Exactly one request succeeds (HTTP 200).
      2. The competing request receives a defined conflict response (HTTP 409).
      3. Exactly one active ride is assigned to the driver in the database.
      4. The driver profile status is BUSY.
    """
    concur_db_path = f"./test_concur_{uuid.uuid4().hex[:8]}.db"
    concur_engine = create_async_engine(f"sqlite+aiosqlite:///{concur_db_path}")
    concur_sessionmaker = async_sessionmaker(bind=concur_engine, class_=AsyncSession, expire_on_commit=False)

    async with concur_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with concur_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Register Rider 1 and Rider 2
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "r1@test.com",
                    "password": "pass123",
                    "full_name": "R1",
                    "role": "RIDER",
                },
            )
            r1_token = (
                await client.post(
                    "/api/v1/auth/login", json={"email": "r1@test.com", "password": "pass123"}
                )
            ).json()["access_token"]

            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "r2@test.com",
                    "password": "pass123",
                    "full_name": "R2",
                    "role": "RIDER",
                },
            )
            r2_token = (
                await client.post(
                    "/api/v1/auth/login", json={"email": "r2@test.com", "password": "pass123"}
                )
            ).json()["access_token"]

            # 2. Register Driver and set ONLINE
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "d1@test.com",
                    "password": "pass123",
                    "full_name": "D1",
                    "role": "DRIVER",
                },
            )
            d1_token = (
                await client.post(
                    "/api/v1/auth/login", json={"email": "d1@test.com", "password": "pass123"}
                )
            ).json()["access_token"]
            await client.post(
                "/api/v1/drivers/register",
                headers={"Authorization": f"Bearer {d1_token}"},
                json={
                    "vehicle_make": "Honda",
                    "vehicle_model": "Civic",
                    "vehicle_plate": "CONCUR-1",
                },
            )
            await client.patch(
                "/api/v1/drivers/status",
                headers={"Authorization": f"Bearer {d1_token}"},
                json={"status": "ONLINE"},
            )

            # 3. Rider 1 and Rider 2 create separate rides
            ride1_resp = await client.post(
                "/api/v1/rides",
                headers={"Authorization": f"Bearer {r1_token}"},
                json={
                    "pickup_latitude": 40.71,
                    "pickup_longitude": -74.00,
                    "pickup_address": "Point A",
                    "dropoff_latitude": 40.75,
                    "dropoff_longitude": -73.98,
                    "dropoff_address": "Point B",
                },
            )
            ride1_id = ride1_resp.json()["id"]

            ride2_resp = await client.post(
                "/api/v1/rides",
                headers={"Authorization": f"Bearer {r2_token}"},
                json={
                    "pickup_latitude": 40.72,
                    "pickup_longitude": -74.01,
                    "pickup_address": "Point C",
                    "dropoff_latitude": 40.76,
                    "dropoff_longitude": -73.97,
                    "dropoff_address": "Point D",
                },
            )
            ride2_id = ride2_resp.json()["id"]

            # 4. Trigger simultaneous concurrent assignment for the SAME driver
            task1 = client.post(
                f"/api/v1/rides/{ride1_id}/accept",
                headers={"Authorization": f"Bearer {d1_token}"},
            )
            task2 = client.post(
                f"/api/v1/rides/{ride2_id}/accept",
                headers={"Authorization": f"Bearer {d1_token}"},
            )

            resps = await asyncio.gather(task1, task2)
            status_codes = sorted([r.status_code for r in resps])

            # Invariant: Exactly one winner (200 OK) and one conflict (409 Conflict)
            assert status_codes == [200, 409], f"Expected [200, 409], got {status_codes}"

            # 5. Verify database consistency via driver endpoint
            driver_check = await client.get(
                "/api/v1/drivers/me", headers={"Authorization": f"Bearer {d1_token}"}
            )
            driver_data = driver_check.json()
            assert driver_data["status"] == "BUSY"

        # 6. Direct DB verification: Exactly 1 active ride assigned
        async with concur_sessionmaker() as session:
            driver_obj = (await session.execute(select(Driver).where(Driver.id == uuid.UUID(driver_data["id"])))).scalar_one()
            assert driver_obj.status.value == "BUSY"

            active_rides_stmt = select(Ride).where(
                Ride.driver_id == driver_obj.id,
                Ride.status.in_([RideStatus.ACCEPTED, RideStatus.ARRIVED, RideStatus.IN_PROGRESS]),
            )
            active_rides = (await session.execute(active_rides_stmt)).scalars().all()
            assert len(active_rides) == 1
    finally:
        app.dependency_overrides.clear()
        await concur_engine.dispose()
        if os.path.exists(concur_db_path):
            try:
                os.remove(concur_db_path)
            except OSError:
                pass
