"""Maps to report Table 5.3 test cases TC-01 ... TC-08 (TC-06 offline is a frontend test)."""
from datetime import timedelta

from app.db import get_conn
from app.timeutil import iso, utcnow

KEY = {"X-API-Key": "dev-operator-key"}


def gps(client, bus="TN30-1234", lat=11.6745, lon=78.1655, ts=None, speed=20.0):
    ts = ts or utcnow()
    return client.post("/api/v1/gps-updates", json={
        "bus_id": bus, "latitude": lat, "longitude": lon, "timestamp": iso(ts), "speed_kmh": speed})


def test_tc01_valid_update_accepted_and_stored(client):
    r = gps(client)
    assert r.status_code == 201 and r.json()["accepted"] is True


def test_tc02_invalid_coordinates_rejected_and_logged(client):
    r = gps(client, lat=123.0)
    assert r.status_code == 422 and "latitude" in r.json()["detail"]["reason"]
    conn = get_conn()
    assert conn.execute("SELECT COUNT(*) FROM rejected_update").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM gps_update").fetchone()[0] == 0


def test_validation_future_old_jump_and_unknown_bus(client):
    assert gps(client, ts=utcnow() + timedelta(minutes=5)).status_code == 422
    assert gps(client).status_code == 201
    assert gps(client, ts=utcnow() - timedelta(minutes=1)).status_code == 422   # older than previous
    assert gps(client, lat=12.5, lon=79.5).status_code == 422                    # teleport
    assert gps(client, bus="NOPE").status_code == 404


def test_tc03_latest_location_with_age(client):
    gps(client)
    j = client.get("/api/v1/buses/TN30-1234/location").json()
    assert j["latitude"] == 11.6745 and j["stale"] is False and j["age_seconds"] < 5


def test_tc04_route_search_and_ordered_stops(client):
    routes = client.get("/api/v1/routes", params={"query": "R12"}).json()
    assert len(routes) == 1
    stops = client.get(f"/api/v1/routes/{routes[0]['route_id']}/stops").json()
    assert [s["sequence_number"] for s in stops] == [1, 2, 3, 4, 5]
    assert client.get("/api/v1/routes", params={"query": "TN30-7777"}).json()[0]["route_name"] == "R07"


def test_tc05_stale_location_flagged(client):
    gps(client, ts=utcnow() - timedelta(minutes=5))
    j = client.get("/api/v1/buses/TN30-1234/eta", params={"stop_id": 5}).json()
    assert j["status"] == "LIVE DATA UNAVAILABLE"
    assert client.get("/api/v1/buses/TN30-1234/location").json()["stale"] is True


def test_tc07_eta_for_selected_stop_is_recorded(client):
    gps(client, lon=78.1655, speed=20)
    j = client.get("/api/v1/buses/TN30-1234/eta", params={"stop_id": 5}).json()
    assert j["status"] == "OK" and j["eta_minutes"] > 0 and j["stop_name"] == "College stop"
    assert get_conn().execute("SELECT COUNT(*) FROM eta_result").fetchone()[0] == 1


def test_eta_wrong_stop_for_route(client):
    assert client.get("/api/v1/buses/TN30-1234/eta", params={"stop_id": 7}).status_code == 404


def test_tc08_delay_alert_when_threshold_exceeded(client):
    # trip started 40 min ago, bus is only at the 2nd stop => badly late
    conn = get_conn()
    conn.execute("UPDATE bus SET trip_start=? WHERE bus_id='TN30-1234'", (iso(utcnow() - timedelta(minutes=40)),))
    conn.commit()
    gps(client, lon=78.1655, speed=20)
    alerts = client.get("/api/v1/alerts").json()["alerts"]
    delay = [a for a in alerts if a["type"] == "DELAY" and a["bus_id"] == "TN30-1234"]
    assert delay and delay[0]["severity"] == "critical"
    # buses that never reported are shown as 'live data unavailable', not as on time
    assert any(a["type"] == "STALE" and a["bus_id"] == "TN30-7777" for a in alerts)


def test_operator_endpoints_need_key(client):
    body = {"route_name": "R99", "start_point": "A", "end_point": "B"}
    assert client.post("/api/v1/operator/routes", json=body).status_code == 401
    assert client.post("/api/v1/operator/routes", json=body, headers=KEY).status_code == 201
    assert client.post("/api/v1/operator/routes", json=body, headers=KEY).status_code == 409


def test_start_trip(client):
    r = client.post("/api/v1/operator/buses/TN30-1234/start-trip", headers=KEY)
    assert r.status_code == 200 and "trip_start" in r.json()
