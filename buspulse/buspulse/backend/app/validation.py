"""Validation rules from report section 4.4 (supports TC-02 and TC-05)."""
import math
from datetime import datetime, timedelta
from typing import Optional, Tuple

from . import config
from .eta import haversine_km


def validate_update(
    lat: float,
    lon: float,
    ts: datetime,
    now: datetime,
    prev: Optional[Tuple[float, float, datetime]] = None,
) -> Optional[str]:
    """Return None if valid, otherwise a human-readable rejection reason."""
    if any(math.isnan(v) or math.isinf(v) for v in (lat, lon)):
        return "coordinates are not finite numbers"
    if not -90 <= lat <= 90:
        return "latitude out of range (-90..90)"
    if not -180 <= lon <= 180:
        return "longitude out of range (-180..180)"
    if ts > now + timedelta(seconds=config.CLOCK_TOLERANCE_S):
        return "timestamp is in the future"
    if prev is not None:
        plat, plon, pts = prev
        if ts <= pts:
            return "timestamp is not newer than the previous stored update"
        hours = (ts - pts).total_seconds() / 3600.0
        kmh = haversine_km(plat, plon, lat, lon) / hours
        if kmh > config.MAX_PLAUSIBLE_KMH:
            return f"position jump not plausible for a bus (~{kmh:.0f} km/h)"
    return None
