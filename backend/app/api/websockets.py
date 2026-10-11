import json

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.core.ws_manager import ws_manager
from app.services.location_cache import redis_store
from app.services.spatial import coords_to_h3

router = APIRouter(tags=["WebSockets"])


def authenticate_ws_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload.get("sub"), payload.get("role")
    except Exception:
        return None, None


@router.websocket("/ws/rides/{ride_id}")
async def ride_tracking_websocket(websocket: WebSocket, ride_id: str, token: str = Query(...)):
    """Rider or Driver subscribes to real-time status and live GPS tracking for an active ride."""
    user_id, role = authenticate_ws_token(token)
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    ws_manager.subscribe_to_ride(ride_id, websocket)

    try:
        while True:
            # Keep socket alive and receive client pings/messages
            data = await websocket.receive_text()
            # If driver transmits location through this socket:
            try:
                msg = json.loads(data)
                if msg.get("type") == "DRIVER_LOCATION" and role == "DRIVER":
                    lat = msg.get("latitude")
                    lng = msg.get("longitude")
                    if lat is not None and lng is not None:
                        h3_cell = coords_to_h3(lat, lng)
                        await redis_store.update_driver_location(user_id, lat, lng, h3_cell)
                        # Fan out coordinates to the rider on this ride
                        await ws_manager.broadcast_to_ride(
                            ride_id,
                            {
                                "type": "DRIVER_LOCATION_UPDATE",
                                "driver_id": user_id,
                                "latitude": lat,
                                "longitude": lng,
                            },
                        )
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.unsubscribe_from_ride(ride_id, websocket)
