import h3

from app.core.config import settings


def coords_to_h3(
    latitude: float, longitude: float, resolution: int = settings.H3_RESOLUTION
) -> str:
    """Convert latitude/longitude coordinates to an H3 index (compatible with H3 v3 & v4)."""
    if hasattr(h3, "latlng_to_cell"):
        return h3.latlng_to_cell(latitude, longitude, resolution)
    elif hasattr(h3, "lat_lng_to_cell"):
        return h3.lat_lng_to_cell(latitude, longitude, resolution)
    elif hasattr(h3, "geo_to_h3"):
        return h3.geo_to_h3(latitude, longitude, resolution)
    raise RuntimeError("Compatible H3 coordinate conversion function not found.")


def get_search_cells(
    latitude: float, longitude: float, k_rings: int = 1, resolution: int = settings.H3_RESOLUTION
) -> set[str]:
    """Retrieve the central cell plus all immediate k-ring neighboring cells."""
    center_cell = coords_to_h3(latitude, longitude, resolution)
    if hasattr(h3, "grid_disk"):
        return set(h3.grid_disk(center_cell, k_rings))
    elif hasattr(h3, "k_ring"):
        return set(h3.k_ring(center_cell, k_rings))
    return {center_cell}
