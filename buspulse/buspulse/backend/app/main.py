"""BUSPULSE REST API (report Table 3.6) + small operator endpoints (FR-10)."""
import hmac
import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .db import get_conn, get_db, init_db
from .eta import estimate_eta
from .models import BusIn, GpsUpdateIn, RouteIn, StopIn
from .seed import seed
from .timeutil import iso, parse, to_utc, utcnow
from .validation import validate_update

log = logging.getLogger("buspulse")
API = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if config.AUTO_SEED:
        conn = get_conn()
        try:
            seed(conn)
        finally:
            conn.close()
    yield


app = FastAPI(title="BUSPULSE API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------- helpers
def require_operator(x_api_key: Optional[str] = Header(default=None)):
    if not x_api_key or not hmac.compare_digest(x_api_key, config.OPERATOR_KEY):
        raise HTTPException(401, "operator API key required (X-API-Key header)")


def _bus_or_404(conn: sqlite3.Connection, bus_id: str) -> sqlite3.Row:
    bus = conn.execute("SELECT * FROM bus WHERE bus_id=?", (bus_id,)).fetchone()
    if not bus:
        raise HTTPException(404, f"unknown bus_id {bus_id}")
    return bus


def _stops(conn: sqlite3.Connection, route_id: int) -> List[dict]:
    rows = conn.execute("SELECT * FROM stop WHERE route_id=? ORDER BY sequence_number", (route_id,)).fetchall()
    return [dict(r) for r in rows]


def _latest(conn: sqlite3.Connection, bus_id: str) -> Optional[dict]:
    r = conn.execute(
        "SELECT latitude, longitude, ts, speed_kmh FROM gps_update WHERE bus_id=? ORDER BY ts DESC LIMIT 1", (bus_id,)
    ).fetchone()
    if not r:
        return None
    return {"latitude": r["latitude"], "longitude": r["longitude"], "ts": parse(r["ts"]), "speed_kmh": r["speed_kmh"]}


def _recent_speeds(conn: sqlite3.Connection, bus_id: str, n: int = 6) -> List[Optional[float]]:
    """Reported speed if present, else speed derived from consecutive positions."""
    from .eta import haversine_km

    rows = conn.execute(
        "SELECT latitude, longitude, ts, speed_kmh FROM gps_update WHERE bus_id=? ORDER BY ts DESC LIMIT ?", (bus_id, n)
    ).fetchall()[::-1]
    out, prev = [], None
    for r in rows:
        if r["speed_kmh"] is not None:
            out.append(r["speed_kmh"])
        elif prev is not None:
            dt = (parse(r["ts"]) - parse(prev["ts"])).total_seconds()
            out.append(haversine_km(prev["latitude"], prev["longitude"], r["latitude"], r["longitude"]) / (dt / 3600) if dt > 0 else None)
        prev = r
    return out


def _eta_for(conn, bus: sqlite3.Row, stops: List[dict], idx: int) -> dict:
    trip_start = parse(bus["trip_start"]) if bus["trip_start"] else None
    return estimate_eta(_latest(conn, bus["bus_id"]), stops, idx, _recent_speeds(conn, bus["bus_id"]), utcnow(), trip_start)


# ---------------------------------------------------------------- public API
@app.get(f"{API}/health")
def health():
    return {"status": "ok", "time": iso(utcnow())}


@app.post(f"{API}/gps-updates", status_code=201)
def post_gps_update(u: GpsUpdateIn, conn: sqlite3.Connection = Depends(get_db)):
    received = utcnow()
    bus = _bus_or_404(conn, u.bus_id)
    ts = to_utc(u.timestamp)
    prev_row = conn.execute(
        "SELECT latitude, longitude, ts FROM gps_update WHERE bus_id=? ORDER BY ts DESC LIMIT 1", (u.bus_id,)
    ).fetchone()
    prev = (prev_row["latitude"], prev_row["longitude"], parse(prev_row["ts"])) if prev_row else None

    reason = validate_update(u.latitude, u.longitude, ts, received, prev)
    if reason:
        conn.execute(
            "INSERT INTO rejected_update (bus_id,reason,payload,received_at) VALUES (?,?,?,?)",
            (u.bus_id, reason, json.dumps(json.loads(u.model_dump_json())), iso(received)),
        )
        conn.commit()
        log.warning("rejected GPS update from %s: %s", u.bus_id, reason)
        raise HTTPException(422, {"accepted": False, "reason": reason})

    cur = conn.execute(
        "INSERT INTO gps_update (bus_id,latitude,longitude,ts,speed_kmh,received_at) VALUES (?,?,?,?,?,?)",
        (u.bus_id, u.latitude, u.longitude, iso(ts), u.speed_kmh, iso(received)),
    )
    conn.execute("UPDATE bus SET last_updated=? WHERE bus_id=?", (iso(ts), u.bus_id))
    conn.commit()
    return {"accepted": True, "update_id": cur.lastrowid, "latency_seconds": round((received - ts).total_seconds(), 3)}


@app.get(f"{API}/buses/{{bus_id}}/location")
def get_location(bus_id: str, conn: sqlite3.Connection = Depends(get_db)):
    _bus_or_404(conn, bus_id)
    loc = _latest(conn, bus_id)
    if not loc:
        raise HTTPException(404, "no location received yet")
    age = (utcnow() - loc["ts"]).total_seconds()
    return {
        "bus_id": bus_id,
        "latitude": loc["latitude"],
        "longitude": loc["longitude"],
        "speed_kmh": loc["speed_kmh"],
        "timestamp": iso(loc["ts"]),
        "age_seconds": round(age, 1),
        "stale": age > config.STALE_LIMIT_S,
    }


@app.get(f"{API}/routes")
def search_routes(query: str = Query(default=""), conn: sqlite3.Connection = Depends(get_db)):
    like = f"%{query.strip()}%"
    rows = conn.execute(
        """SELECT DISTINCT r.* FROM route r LEFT JOIN bus b ON b.route_id=r.route_id
           WHERE r.route_name LIKE ? OR r.start_point LIKE ? OR r.end_point LIKE ? OR b.bus_id LIKE ?
           ORDER BY r.route_name""",
        (like, like, like, like),
    ).fetchall()
    return [dict(r) for r in rows]


@app.get(f"{API}/routes/{{route_id}}/stops")
def route_stops(route_id: int, conn: sqlite3.Connection = Depends(get_db)):
    if not conn.execute("SELECT 1 FROM route WHERE route_id=?", (route_id,)).fetchone():
        raise HTTPException(404, "unknown route")
    return _stops(conn, route_id)


@app.get(f"{API}/buses/{{bus_id}}/eta")
def bus_eta(bus_id: str, stop_id: int = Query(...), conn: sqlite3.Connection = Depends(get_db)):
    bus = _bus_or_404(conn, bus_id)
    stops = _stops(conn, bus["route_id"])
    idx = next((i for i, s in enumerate(stops) if s["stop_id"] == stop_id), None)
    if idx is None:
        raise HTTPException(404, "stop does not belong to this bus's route")
    result = _eta_for(conn, bus, stops, idx)
    conn.execute(
        "INSERT INTO eta_result (bus_id,stop_id,estimated_arrival,calculated_at,status) VALUES (?,?,?,?,?)",
        (bus_id, stop_id, result.get("eta"), iso(utcnow()), result["status"] if result["status"] != "OK" else result["state"]),
    )
    conn.commit()
    return {"bus_id": bus_id, "stop_id": stop_id, "stop_name": stops[idx]["stop_name"], **result}


@app.get(f"{API}/buses")
def list_buses(conn: sqlite3.Connection = Depends(get_db)):
    """Dashboard list: every bus with route, freshness and ETA to the route's last stop."""
    out = []
    for bus in conn.execute("SELECT b.*, r.route_name, r.end_point FROM bus b JOIN route r USING(route_id) ORDER BY b.bus_id"):
        stops = _stops(conn, bus["route_id"])
        res = _eta_for(conn, bus, stops, len(stops) - 1) if stops else {"status": "LIVE DATA UNAVAILABLE", "state": "UNKNOWN"}
        loc = _latest(conn, bus["bus_id"])
        out.append(
            {
                "bus_id": bus["bus_id"],
                "route_id": bus["route_id"],
                "route_name": bus["route_name"],
                "destination": bus["end_point"],
                "location": None if not loc else {"latitude": loc["latitude"], "longitude": loc["longitude"]},
                "final_stop_id": stops[-1]["stop_id"] if stops else None,
                **res,
            }
        )
    return out


@app.get(f"{API}/alerts")
def alerts(conn: sqlite3.Connection = Depends(get_db)):
    items = []
    for b in list_buses(conn):
        if b["status"] == "LIVE DATA UNAVAILABLE":
            items.append({"type": "STALE", "severity": "info", "bus_id": b["bus_id"], "route_name": b["route_name"],
                          "message": f"{b['route_name']} ({b['bus_id']}): live data unavailable. Last update: {b.get('last_updated') or 'never'}"})
        elif b["state"] in ("SLIGHT DELAY", "DELAYED"):
            items.append({"type": "DELAY", "severity": "warning" if b["state"] == "SLIGHT DELAY" else "critical",
                          "bus_id": b["bus_id"], "route_name": b["route_name"],
                          "message": f"{b['route_name']} ({b['bus_id']}) is about {round(b['delay_minutes'])} min late. New ETA at {b['destination']}: {b['eta_minutes']} min"})
    return {"generated_at": iso(utcnow()), "alerts": items}


# ---------------------------------------------------------------- operator API
@app.post(f"{API}/operator/routes", status_code=201, dependencies=[Depends(require_operator)])
def create_route(r: RouteIn, conn: sqlite3.Connection = Depends(get_db)):
    try:
        cur = conn.execute("INSERT INTO route (route_name,start_point,end_point) VALUES (?,?,?)", (r.route_name, r.start_point, r.end_point))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "route name already exists")
    conn.commit()
    return {"route_id": cur.lastrowid}


@app.post(f"{API}/operator/routes/{{route_id}}/stops", status_code=201, dependencies=[Depends(require_operator)])
def create_stop(route_id: int, s: StopIn, conn: sqlite3.Connection = Depends(get_db)):
    try:
        cur = conn.execute(
            "INSERT INTO stop (route_id,stop_name,latitude,longitude,sequence_number,scheduled_offset_min) VALUES (?,?,?,?,?,?)",
            (route_id, s.stop_name, s.latitude, s.longitude, s.sequence_number, s.scheduled_offset_min),
        )
    except sqlite3.IntegrityError as e:
        raise HTTPException(409, f"cannot create stop: {e}")
    conn.commit()
    return {"stop_id": cur.lastrowid}


@app.post(f"{API}/operator/buses", status_code=201, dependencies=[Depends(require_operator)])
def create_bus(b: BusIn, conn: sqlite3.Connection = Depends(get_db)):
    try:
        conn.execute("INSERT INTO bus (bus_id,registration,route_id) VALUES (?,?,?)", (b.bus_id, b.registration, b.route_id))
    except sqlite3.IntegrityError as e:
        raise HTTPException(409, f"cannot create bus: {e}")
    conn.commit()
    return {"bus_id": b.bus_id}


@app.post(f"{API}/operator/buses/{{bus_id}}/start-trip", dependencies=[Depends(require_operator)])
def start_trip(bus_id: str, conn: sqlite3.Connection = Depends(get_db)):
    _bus_or_404(conn, bus_id)
    now = iso(utcnow())
    conn.execute("UPDATE bus SET trip_start=? WHERE bus_id=?", (now, bus_id))
    conn.commit()
    return {"bus_id": bus_id, "trip_start": now}
