"""Baseline ETA + delay estimation (report section 4.5).

ETA = now + d / v, where d is the remaining ROUTE distance (bus -> next stop ->
... -> selected stop, haversine segments) and v is a smoothed, clamped speed.
"""
import math
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from . import config
from .timeutil import iso

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def next_stop_index(lat: float, lon: float, stops: Sequence[dict]) -> int:
    """Index (into the ordered stop list) of the next stop the bus will reach.

    Picks the route segment with the smallest 'detour'
    d(bus,A) + d(bus,B) - d(A,B); the next stop is the segment's end B.
    Limitation: a bus before the first stop is treated as on segment 0.
    """
    if len(stops) == 1:
        return 0
    best_k, best_detour = 0, float("inf")
    for k in range(len(stops) - 1):
        a, b = stops[k], stops[k + 1]
        detour = (
            haversine_km(lat, lon, a["latitude"], a["longitude"])
            + haversine_km(lat, lon, b["latitude"], b["longitude"])
            - haversine_km(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
        )
        if detour < best_detour:
            best_k, best_detour = k, detour
    return best_k + 1


def remaining_distance_km(lat: float, lon: float, stops: Sequence[dict], selected_index: int) -> Optional[float]:
    """None if the bus has already passed the selected stop."""
    ni = next_stop_index(lat, lon, stops)
    if selected_index < ni:
        return None
    d = haversine_km(lat, lon, stops[ni]["latitude"], stops[ni]["longitude"])
    for k in range(ni, selected_index):
        a, b = stops[k], stops[k + 1]
        d += haversine_km(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
    return d


def smoothed_speed(speeds: Sequence[Optional[float]], alpha: float = None) -> Optional[float]:
    """Exponential moving average, oldest -> newest. None if no data."""
    alpha = config.EMA_ALPHA if alpha is None else alpha
    ema = None
    for s in speeds:
        if s is None:
            continue
        ema = s if ema is None else alpha * s + (1 - alpha) * ema
    return ema


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def classify_delay(delay_min: Optional[float]) -> str:
    if delay_min is None:
        return "NO SCHEDULE"
    if delay_min < config.T1_MIN:
        return "ON TIME"
    if delay_min < config.T2_MIN:
        return "SLIGHT DELAY"
    return "DELAYED"


def estimate_eta(
    loc: Optional[dict],
    stops: List[dict],
    selected_index: int,
    speeds: Sequence[Optional[float]],
    now: datetime,
    trip_start: Optional[datetime] = None,
) -> dict:
    """loc = {"latitude","longitude","ts": aware datetime}. Pure function (easy to test)."""
    if loc is None:
        return {"status": "LIVE DATA UNAVAILABLE", "state": "UNKNOWN", "last_updated": None, "age_seconds": None}

    age = (now - loc["ts"]).total_seconds()
    base = {"last_updated": iso(loc["ts"]), "age_seconds": round(age, 1)}
    if age > config.STALE_LIMIT_S:
        return {**base, "status": "LIVE DATA UNAVAILABLE", "state": "UNKNOWN"}

    d = remaining_distance_km(loc["latitude"], loc["longitude"], stops, selected_index)
    if d is None:
        return {**base, "status": "PASSED", "state": "PASSED"}

    raw = smoothed_speed(speeds)
    assumed = raw is None
    v = clamp(config.DEFAULT_SPEED_KMH if assumed else raw, config.V_MIN_KMH, config.V_MAX_KMH)
    minutes = d / v * 60.0
    eta_dt = now + timedelta(minutes=minutes)

    delay = None
    offset = stops[selected_index].get("scheduled_offset_min")
    if trip_start is not None and offset is not None:
        scheduled = trip_start + timedelta(minutes=offset)
        delay = (eta_dt - scheduled).total_seconds() / 60.0

    return {
        **base,
        "status": "OK",
        "state": classify_delay(delay),
        "eta": iso(eta_dt),
        "eta_minutes": round(minutes, 1),
        "distance_km": round(d, 2),
        "speed_kmh": round(v, 1),
        "assumed_speed": assumed,
        "delay_minutes": None if delay is None else round(delay, 1),
    }
