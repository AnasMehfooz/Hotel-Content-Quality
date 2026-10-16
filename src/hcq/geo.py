"""Small geodesy helpers (WGS84, spherical approximation)."""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088
METERS_PER_DEG_LAT = 111_320.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def offset(lat: float, lon: float, meters: float, bearing_deg: float) -> tuple[float, float]:
    """Move a point by ``meters`` along ``bearing_deg`` (0 = north). Good to ~0.1% at city scale."""
    b = math.radians(bearing_deg)
    dlat = meters * math.cos(b) / METERS_PER_DEG_LAT
    dlon = meters * math.sin(b) / (METERS_PER_DEG_LAT * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon
