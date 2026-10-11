from app.services.pricing import calculate_fare, haversine_distance_km


def test_haversine_distance_known_coordinates():
    # Times Square (40.7580, -73.9855) to Central Park (40.785091, -73.968285)
    # Approx ~3.3 to 3.5 km straight line
    dist = haversine_distance_km(40.7580, -73.9855, 40.785091, -73.968285)
    assert 3.0 <= dist <= 3.7


def test_haversine_distance_zero():
    dist = haversine_distance_km(37.7749, -122.4194, 37.7749, -122.4194)
    assert dist == 0.0


def test_calculate_fare_deterministic_values():
    fare = calculate_fare(distance_km=10.0)
    # distance = 10.0, speed = 30 km/h -> duration = 20 mins
    # base = 2.50
    # distance_fare = 10.0 * 1.20 = 12.00
    # time_fare = 20.0 * 0.25 = 5.00
    # total = 2.50 + 12.00 + 5.00 = 19.50
    assert fare.distance_km == 10.0
    assert fare.estimated_duration_minutes == 20.0
    assert fare.base_fare == 2.50
    assert fare.distance_fare == 12.00
    assert fare.time_fare == 5.00
    assert fare.total_fare == 19.50
    assert fare.currency == "USD"


def test_calculate_fare_minimum_bound():
    # Very short distance (e.g. 0.1 km) should clamp to 0.5 km minimum
    fare = calculate_fare(distance_km=0.1)
    assert fare.distance_km == 0.5
    assert fare.total_fare > 2.50
