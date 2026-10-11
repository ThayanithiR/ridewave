import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Driver, DriverStatus
from app.services.location_cache import redis_store
from app.services.pricing import haversine_distance_km
from app.services.spatial import get_search_cells


async def find_nearby_drivers(
    pickup_lat: float,
    pickup_lng: float,
    max_radius_km: float,
    db: AsyncSession,
) -> list[dict]:
    """
    Two-Tiered Spatial Search:
    Tier 1: Retrieve candidate driver IDs from H3 hexagon buckets in Redis.
    Tier 2: Filter and rank candidates by actual distance and eligibility in PostgreSQL.
    """
    search_cells = list(get_search_cells(pickup_lat, pickup_lng, k_rings=2))
    candidate_driver_ids = await redis_store.get_drivers_in_cells(search_cells)

    # If Redis returns candidates, filter them; otherwise fallback to DB last known coordinates
    drivers_query = select(Driver).where(Driver.status == DriverStatus.ONLINE)
    if candidate_driver_ids:
        try:
            valid_uuids = [uuid.UUID(did) for did in candidate_driver_ids]
            drivers_query = drivers_query.where(Driver.id.in_(valid_uuids))
        except ValueError:
            pass

    result = await db.execute(drivers_query)
    online_drivers = result.scalars().all()

    ranked_candidates = []
    for driver in online_drivers:
        # Check latest ephemeral location first, fallback to DB last coords
        ephemeral = await redis_store.get_driver_location(str(driver.id))
        if ephemeral:
            d_lat = ephemeral["latitude"]
            d_lng = ephemeral["longitude"]
        elif driver.last_latitude and driver.last_longitude:
            d_lat = float(driver.last_latitude)
            d_lng = float(driver.last_longitude)
        else:
            continue

        dist_km = haversine_distance_km(pickup_lat, pickup_lng, d_lat, d_lng)
        if dist_km <= max_radius_km:
            ranked_candidates.append(
                {
                    "driver_id": str(driver.id),
                    "vehicle_make": driver.vehicle_make,
                    "vehicle_model": driver.vehicle_model,
                    "vehicle_plate": driver.vehicle_plate,
                    "latitude": d_lat,
                    "longitude": d_lng,
                    "distance_km": dist_km,
                }
            )

    # Sort strictly by closest distance
    ranked_candidates.sort(key=lambda x: x["distance_km"])
    return ranked_candidates
