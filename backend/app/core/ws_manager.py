import json

from fastapi import WebSocket


class WebSocketConnectionManager:
    def __init__(self):
        # Mapping: ride_id -> Set of active WebSocket connections
        self.ride_subscribers: dict[str, set[WebSocket]] = {}
        # Mapping: user_id -> WebSocket
        self.user_connections: dict[str, WebSocket] = {}

    async def connect_user(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.user_connections[user_id] = websocket

    def disconnect_user(self, user_id: str):
        self.user_connections.pop(user_id, None)

    def subscribe_to_ride(self, ride_id: str, websocket: WebSocket):
        if ride_id not in self.ride_subscribers:
            self.ride_subscribers[ride_id] = set()
        self.ride_subscribers[ride_id].add(websocket)

    def unsubscribe_from_ride(self, ride_id: str, websocket: WebSocket):
        if ride_id in self.ride_subscribers:
            self.ride_subscribers[ride_id].discard(websocket)
            if not self.ride_subscribers[ride_id]:
                del self.ride_subscribers[ride_id]

    async def broadcast_to_ride(self, ride_id: str, message: dict):
        """Fan out real-time GPS coordinates and ride state updates to subscribed clients."""
        subscribers = self.ride_subscribers.get(ride_id, set()).copy()
        dead_connections = set()
        payload = json.dumps(message)

        for ws in subscribers:
            try:
                await ws.send_text(payload)
            except Exception:
                dead_connections.add(ws)

        for dead_ws in dead_connections:
            self.unsubscribe_from_ride(ride_id, dead_ws)


ws_manager = WebSocketConnectionManager()
