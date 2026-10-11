import math

from app.schemas import FareEstimateResponse

# Deterministic fare calculation constants
BASE_FARE = 2.50
PER_KM_RATE = 1.20
PER_MINUTE_RATE = 0.25
AVERAGE_SPEED_KMH = 30.0  # Urban traffic assumption


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in km."""
    R = 6371.0  # Earth's radius in kilometers

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return round(R * c, 2)


def calculate_fare(distance_km: float) -> FareEstimateResponse:
    """Deterministic formula for fare calculation."""
    # Ensure minimum distance
    distance = max(distance_km, 0.5)
    duration_hours = distance / AVERAGE_SPEED_KMH
    duration_minutes = round(duration_hours * 60, 1)

    distance_fare = round(distance * PER_KM_RATE, 2)
    time_fare = round(duration_minutes * PER_MINUTE_RATE, 2)
    total_fare = round(BASE_FARE + distance_fare + time_fare, 2)

    return FareEstimateResponse(
        distance_km=distance,
        estimated_duration_minutes=duration_minutes,
        base_fare=BASE_FARE,
        distance_fare=distance_fare,
        time_fare=time_fare,
        total_fare=total_fare,
        currency="USD",
    )
