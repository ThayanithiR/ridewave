import asyncio
from collections.abc import Generator

from app.core.ws_manager import ws_manager
from app.services.location_cache import redis_store
from app.services.spatial import coords_to_h3


def interpolate_route(
    start: tuple[float, float],
    end: tuple[float, float],
    steps: int = 20,
) -> Generator[tuple[float, float], None, None]:
    """Generate intermediate latitude/longitude steps between start and destination."""
    lat1, lng1 = start
    lat2, lng2 = end
    for i in range(steps + 1):
        ratio = i / steps
        cur_lat = round(lat1 + (lat2 - lat1) * ratio, 6)
        cur_lng = round(lng1 + (lng2 - lng1) * ratio, 6)
        yield (cur_lat, cur_lng)


async def run_driver_simulation(
    driver_id: str,
    ride_id: str,
    start_coords: tuple[float, float],
    target_coords: tuple[float, float],
    step_delay_seconds: float = 0.5,
):
    """
    Simulates a virtual driver moving towards a target coordinate,
    publishing high-frequency GPS pings to Redis and broadcasting via WebSocket.
    """
    for lat, lng in interpolate_route(start_coords, target_coords, steps=10):
        h3_cell = coords_to_h3(lat, lng)
        await redis_store.update_driver_location(driver_id, lat, lng, h3_cell)
        await ws_manager.broadcast_to_ride(
            ride_id,
            {
                "type": "DRIVER_LOCATION_UPDATE",
                "driver_id": driver_id,
                "latitude": lat,
                "longitude": lng,
            },
        )
        await asyncio.sleep(step_delay_seconds)
