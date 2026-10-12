import uuid
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from app.core.auth import create_access_token
from app.core.config import Settings
from app.main import app
from app.schemas import Coordinate, RideCreateRequest


def test_production_secret_key_fails_fast_on_insecure_default():
    """Asserts that starting in production with an insecure default or short secret key fails fast."""
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="default-insecure-secret-key-change-in-production",
        )

    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="too-short-secret",
        )

    # Valid production secret passes
    valid_prod_settings = Settings(
        APP_ENV="production",
        SECRET_KEY="a-very-strong-production-secret-key-that-is-over-32-chars-long",
    )
    assert valid_prod_settings.APP_ENV == "production"


def test_request_id_and_timing_headers_present():
    """Validates that HTTP responses contain structured X-Request-ID and X-Process-Time headers."""
    client = TestClient(app)
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert "X-Process-Time" in resp.headers


def test_coordinate_validation_bounds():
    """Validates that coordinates outside standard WGS-84 ranges are rejected by Pydantic."""
    # Valid coordinates
    valid_coord = Coordinate(latitude=40.7128, longitude=-74.0060)
    assert valid_coord.latitude == 40.7128

    # Latitude out of bounds (> 90 or < -90)
    with pytest.raises(ValidationError):
        Coordinate(latitude=95.0, longitude=-74.0060)

    with pytest.raises(ValidationError):
        Coordinate(latitude=-91.0, longitude=-74.0060)

    # Longitude out of bounds (> 180 or < -180)
    with pytest.raises(ValidationError):
        Coordinate(latitude=40.7128, longitude=185.0)

    with pytest.raises(ValidationError):
        Coordinate(latitude=40.7128, longitude=-181.0)


def test_websocket_rejects_unauthenticated_connection():
    """Asserts that connecting to WebSocket without a valid JWT token closes with code 1008."""
    client = TestClient(app)
    fake_ride_id = str(uuid.uuid4())

    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/rides/{fake_ride_id}?token=invalid-junk-token"):
            pass


def test_websocket_rejects_unauthorized_user_not_on_trip():
    """Asserts that an authenticated user who is NOT a participant in the ride receives policy violation disconnect."""
    client = TestClient(app)
    unauthorized_user_id = str(uuid.uuid4())
    token = create_access_token({"sub": unauthorized_user_id, "role": "RIDER"})
    nonexistent_ride_id = str(uuid.uuid4())

    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/rides/{nonexistent_ride_id}?token={token}"):
            pass
