import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.events.outbox import TransactionalOutbox
from app.events.schemas import RideRequestedEvent
from app.main import app

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


@pytest.mark.asyncio
async def test_transactional_outbox_pattern():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        # Create domain event
        event = RideRequestedEvent(
            aggregate_id=str(uuid.uuid4()),
            payload={"fare": 18.50, "pickup": "Market St", "dropoff": "Mission St"},
        )
        # Atomically record to outbox in transaction
        await TransactionalOutbox.record_event(session, event)
        await session.commit()

        # Fetch pending
        pending = await TransactionalOutbox.fetch_pending_events(session)
        assert len(pending) == 1
        assert pending[0].event_type == "ride.requested"
        assert pending[0].status == "PENDING"


@pytest.mark.asyncio
async def test_ai_trip_assistant_authorized_tool_isolation():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:

        async def override_get_db():
            yield session

        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Register User A
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "usera@test.com",
                    "password": "password123",
                    "full_name": "User A",
                    "role": "RIDER",
                },
            )
            token_a = (
                await client.post(
                    "/api/v1/auth/login",
                    json={"email": "usera@test.com", "password": "password123"},
                )
            ).json()["access_token"]

            # 2. Register User B
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "userb@test.com",
                    "password": "password123",
                    "full_name": "User B",
                    "role": "RIDER",
                },
            )
            token_b = (
                await client.post(
                    "/api/v1/auth/login",
                    json={"email": "userb@test.com", "password": "password123"},
                )
            ).json()["access_token"]

            # 3. User A books a ride
            await client.post(
                "/api/v1/rides",
                headers={"Authorization": f"Bearer {token_a}"},
                json={
                    "pickup_latitude": 37.77,
                    "pickup_longitude": -122.41,
                    "pickup_address": "User A Pickup",
                    "dropoff_latitude": 37.78,
                    "dropoff_longitude": -122.42,
                    "dropoff_address": "User A Dropoff",
                },
            )

            # 4. User A asks AI assistant
            resp_a = await client.post(
                "/api/v1/assistant/chat",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"message": "What is my last trip?"},
            )
            assert resp_a.status_code == 200
            assert "User A Pickup" in resp_a.json()["response"]

            # 5. User B asks AI assistant - MUST NOT see User A's trips!
            resp_b = await client.post(
                "/api/v1/assistant/chat",
                headers={"Authorization": f"Bearer {token_b}"},
                json={"message": "What is my last trip?"},
            )
            assert resp_b.status_code == 200
            assert "User A Pickup" not in resp_b.json()["response"]

        app.dependency_overrides.clear()
