import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app

# In-memory SQLite async engine for lightning fast and isolated test execution
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_auth_and_user_flows(client: AsyncClient):
    # 1. Register Rider
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "rider@test.com",
            "password": "password123",
            "full_name": "Test Rider",
            "role": "RIDER",
        },
    )
    assert reg_resp.status_code == 201
    rider_data = reg_resp.json()
    assert rider_data["email"] == "rider@test.com"

    # 2. Login Rider
    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": "rider@test.com", "password": "password123"}
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    assert token is not None

    # 3. Get /me
    me_resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["full_name"] == "Test Rider"


@pytest.mark.asyncio
async def test_full_ride_lifecycle(client: AsyncClient):
    # Setup Rider
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "rider@test.com",
            "password": "password123",
            "full_name": "Rider",
            "role": "RIDER",
        },
    )
    rider_token = (
        await client.post(
            "/api/v1/auth/login", json={"email": "rider@test.com", "password": "password123"}
        )
    ).json()["access_token"]

    # Setup Driver
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "driver@test.com",
            "password": "password123",
            "full_name": "Driver",
            "role": "DRIVER",
        },
    )
    driver_token = (
        await client.post(
            "/api/v1/auth/login", json={"email": "driver@test.com", "password": "password123"}
        )
    ).json()["access_token"]

    # Register Driver Profile and set ONLINE
    d_reg = await client.post(
        "/api/v1/drivers/register",
        headers={"Authorization": f"Bearer {driver_token}"},
        json={"vehicle_make": "Toyota", "vehicle_model": "Camry", "vehicle_plate": "NYC-1234"},
    )
    assert d_reg.status_code == 201
    await client.patch(
        "/api/v1/drivers/status",
        headers={"Authorization": f"Bearer {driver_token}"},
        json={"status": "ONLINE"},
    )

    # 1. Rider requests a ride
    ride_req = await client.post(
        "/api/v1/rides",
        headers={"Authorization": f"Bearer {rider_token}"},
        json={
            "pickup_latitude": 40.7128,
            "pickup_longitude": -74.0060,
            "pickup_address": "City Hall, NYC",
            "dropoff_latitude": 40.7589,
            "dropoff_longitude": -73.9851,
            "dropoff_address": "Times Square, NYC",
        },
    )
    assert ride_req.status_code == 201
    ride = ride_req.json()
    ride_id = ride["id"]
    assert ride["status"] == "REQUESTED"
    assert ride["estimated_fare"] > 0

    # 2. Driver accepts the ride
    accept_resp = await client.post(
        f"/api/v1/rides/{ride_id}/accept", headers={"Authorization": f"Bearer {driver_token}"}
    )
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "ACCEPTED"

    # 3. Driver arrives at pickup
    arrive_resp = await client.post(
        f"/api/v1/rides/{ride_id}/arrive", headers={"Authorization": f"Bearer {driver_token}"}
    )
    assert arrive_resp.status_code == 200
    assert arrive_resp.json()["status"] == "ARRIVED"

    # 4. Driver starts ride
    start_resp = await client.post(
        f"/api/v1/rides/{ride_id}/start", headers={"Authorization": f"Bearer {driver_token}"}
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "IN_PROGRESS"

    # 5. Driver completes ride
    complete_resp = await client.post(
        f"/api/v1/rides/{ride_id}/complete", headers={"Authorization": f"Bearer {driver_token}"}
    )
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "COMPLETED"
    assert complete_resp.json()["final_fare"] == ride["estimated_fare"]


@pytest.mark.asyncio
async def test_idempotency_duplicate_ride_prevention(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "rider@test.com",
            "password": "password123",
            "full_name": "Rider",
            "role": "RIDER",
        },
    )
    rider_token = (
        await client.post(
            "/api/v1/auth/login", json={"email": "rider@test.com", "password": "password123"}
        )
    ).json()["access_token"]

    idempotency_key = "test-unique-key-12345"
    payload = {
        "pickup_latitude": 37.7749,
        "pickup_longitude": -122.4194,
        "pickup_address": "Market St, SF",
        "dropoff_latitude": 37.7833,
        "dropoff_longitude": -122.4167,
        "dropoff_address": "Union Square, SF",
        "idempotency_key": idempotency_key,
    }

    # First request
    resp1 = await client.post(
        "/api/v1/rides", headers={"Authorization": f"Bearer {rider_token}"}, json=payload
    )
    assert resp1.status_code == 201

    # Second request with the identical idempotency key returns exact same ride ID, does not create duplicate
    resp2 = await client.post(
        "/api/v1/rides", headers={"Authorization": f"Bearer {rider_token}"}, json=payload
    )
    assert resp2.status_code in [200, 201]
    assert resp1.json()["id"] == resp2.json()["id"]
