import json
import uuid
from datetime import datetime

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.ws_manager import ws_manager
from app.models import Driver, Ride, UserRole
from app.services.location_cache import redis_store
from app.services.spatial import coords_to_h3

router = APIRouter(tags=["WebSockets"])


def authenticate_ws_token(token: str):
    """Verifies JWT bearer token signature and returns user_id, role."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        role = payload.get("role")
        if user_id:
            return uuid.UUID(user_id), role
    except Exception:
        pass
    return None, None


async def authorize_ride_participant(ride_id: uuid.UUID, user_id: uuid.UUID, role: str) -> bool:
    """Verifies that the user is the assigned rider, driver, or an admin for this ride."""
    if role == UserRole.ADMIN.value:
        return True

    async with AsyncSessionLocal() as session:
        ride = (await session.execute(select(Ride).where(Ride.id == ride_id))).scalar_one_or_none()
        if not ride:
            return False

        if ride.rider_id == user_id:
            return True

        if ride.driver_id:
            driver = (
                await session.execute(select(Driver).where(Driver.id == ride.driver_id))
            ).scalar_one_or_none()
            if driver and driver.user_id == user_id:
                return True

        return False


@router.websocket("/ws/rides/{ride_id}")
async def ride_tracking_websocket(websocket: WebSocket, ride_id: str, token: str = Query(...)):
    """
    Rider or Driver subscribes to real-time status and live GPS tracking for an active ride.
    Enforces authentication and strict ride-level participation authorization.
    """
    user_id, role = authenticate_ws_token(token)
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        parsed_ride_id = uuid.UUID(ride_id)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    is_authorized = await authorize_ride_participant(parsed_ride_id, user_id, role)
    if not is_authorized:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    ws_manager.subscribe_to_ride(ride_id, websocket)

    last_sequence_time = 0.0

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                # Location broadcast: only assigned drivers may broadcast driver telemetry
                if msg.get("type") == "DRIVER_LOCATION" and role == "DRIVER":
                    lat = msg.get("latitude")
                    lng = msg.get("longitude")
                    msg_time = msg.get("timestamp", 0.0)

                    # Validate coordinate boundaries
                    if (
                        lat is not None
                        and lng is not None
                        and -90.0 <= lat <= 90.0
                        and -180.0 <= lng <= 180.0
                    ):
                        # Monotonic check to drop stale delayed packets
                        if msg_time and msg_time < last_sequence_time:
                            continue
                        if msg_time:
                            last_sequence_time = msg_time

                        h3_cell = coords_to_h3(lat, lng)
                        await redis_store.update_driver_location(str(user_id), lat, lng, h3_cell)
                        await ws_manager.broadcast_to_ride(
                            ride_id,
                            {
                                "type": "DRIVER_LOCATION_UPDATE",
                                "driver_id": str(user_id),
                                "latitude": lat,
                                "longitude": lng,
                                "timestamp": msg_time or datetime.utcnow().timestamp(),
                            },
                        )
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.unsubscribe_from_ride(ride_id, websocket)
