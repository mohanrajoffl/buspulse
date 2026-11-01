from datetime import datetime, timedelta, timezone

import pytest

from app.eta import (classify_delay, clamp, estimate_eta, haversine_km, next_stop_index,
                     remaining_distance_km, smoothed_speed)

NOW = datetime(2026, 10, 22, 10, 30, tzinfo=timezone.utc)
STOPS = [
    {"stop_id": i + 1, "latitude": 11.6745, "longitude": 78.1548 + 0.0107 * i, "scheduled_offset_min": 3.0 * i}
    for i in range(5)
]


def loc(lon, age=5):
    return {"latitude": 11.6745, "longitude": lon, "ts": NOW - timedelta(seconds=age)}


def test_haversine_one_degree_latitude():
    assert haversine_km(0, 0, 1, 0) == pytest.approx(111.19, abs=0.1)


def test_segment_length_matches_report_table_4_3():
    # report: ~1.17 km between consecutive illustrative stops
    assert haversine_km(*[STOPS[0][k] for k in ("latitude", "longitude")], *[STOPS[1][k] for k in ("latitude", "longitude")]) == pytest.approx(1.17, abs=0.02)


def test_next_stop_and_remaining_distance():
    lon = (STOPS[1]["longitude"] + STOPS[2]["longitude"]) / 2  # between S2 and S3
    assert next_stop_index(11.6745, lon, STOPS) == 2  # next stop = S3 (index 2)
    d = remaining_distance_km(11.6745, lon, STOPS, 4)
    assert d == pytest.approx(0.58 + 1.17 + 1.17, abs=0.05)


def test_passed_stop_returns_none():
    lon = (STOPS[2]["longitude"] + STOPS[3]["longitude"]) / 2
    assert remaining_distance_km(11.6745, lon, STOPS, 1) is None


def test_eta_formula_and_speed_sensitivity():
    lon = (STOPS[1]["longitude"] + STOPS[2]["longitude"]) / 2
    r20 = estimate_eta(loc(lon), STOPS, 4, [20, 20, 20], NOW)
    assert r20["status"] == "OK"
    assert r20["eta_minutes"] == pytest.approx(r20["distance_km"] / 20 * 60, abs=0.1)
    r15 = estimate_eta(loc(lon), STOPS, 4, [15, 15], NOW)
    r25 = estimate_eta(loc(lon), STOPS, 4, [25, 25], NOW)
    assert r15["eta_minutes"] > r20["eta_minutes"] > r25["eta_minutes"]


def test_stale_data_is_reported_honestly():
    r = estimate_eta(loc(78.16, age=300), STOPS, 4, [20], NOW)
    assert r["status"] == "LIVE DATA UNAVAILABLE" and "eta" not in r


def test_no_location():
    assert estimate_eta(None, STOPS, 4, [], NOW)["status"] == "LIVE DATA UNAVAILABLE"


def test_zero_speed_is_clamped_not_infinite():
    r = estimate_eta(loc(78.16), STOPS, 4, [0, 0, 0], NOW)
    assert r["speed_kmh"] == 5.0 and r["eta_minutes"] < 1000


def test_missing_speed_uses_flagged_default():
    assert estimate_eta(loc(78.16), STOPS, 4, [], NOW)["assumed_speed"] is True


def test_delay_classification_thresholds():
    assert [classify_delay(x) for x in (-5, 2.9, 3, 9.9, 10, 40)] == [
        "ON TIME", "ON TIME", "SLIGHT DELAY", "SLIGHT DELAY", "DELAYED", "DELAYED"]
    assert classify_delay(None) == "NO SCHEDULE"


def test_delayed_vs_schedule():
    # trip started 30 min ago: S5 was scheduled 12 min after start => 18 min ago. Bus still ~3 km away.
    r = estimate_eta(loc(STOPS[1]["longitude"]), STOPS, 4, [20], NOW, trip_start=NOW - timedelta(minutes=30))
    assert r["state"] == "DELAYED" and r["delay_minutes"] > 10


def test_smoothing_and_clamp():
    assert smoothed_speed([]) is None
    assert smoothed_speed([None, 10, 20], alpha=0.5) == 15
    assert clamp(100, 5, 60) == 60 and clamp(1, 5, 60) == 5
