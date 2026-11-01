-- BUSPULSE schema (SQLite). Based on report Appendix A, plus alert/audit helpers.
CREATE TABLE IF NOT EXISTS route (
    route_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    route_name   TEXT NOT NULL UNIQUE,
    start_point  TEXT NOT NULL,
    end_point    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bus (
    bus_id        TEXT PRIMARY KEY,
    registration  TEXT,
    route_id      INTEGER NOT NULL REFERENCES route(route_id),
    status        TEXT NOT NULL DEFAULT 'ACTIVE',
    last_updated  TEXT,
    trip_start    TEXT              -- ISO UTC; used with stop.scheduled_offset_min
);
CREATE TABLE IF NOT EXISTS stop (
    stop_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id              INTEGER NOT NULL REFERENCES route(route_id),
    stop_name             TEXT NOT NULL,
    latitude              REAL NOT NULL,
    longitude             REAL NOT NULL,
    sequence_number       INTEGER NOT NULL,
    scheduled_offset_min  REAL,     -- minutes after trip start
    UNIQUE (route_id, sequence_number)
);
CREATE TABLE IF NOT EXISTS gps_update (
    update_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    bus_id       TEXT NOT NULL REFERENCES bus(bus_id),
    latitude     REAL NOT NULL,
    longitude    REAL NOT NULL,
    ts           TEXT NOT NULL,     -- device timestamp, ISO UTC
    speed_kmh    REAL,
    received_at  TEXT NOT NULL      -- server receipt time (for latency measurement)
);
CREATE INDEX IF NOT EXISTS idx_gps_bus_ts ON gps_update (bus_id, ts DESC);
CREATE TABLE IF NOT EXISTS eta_result (
    eta_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    bus_id            TEXT NOT NULL REFERENCES bus(bus_id),
    stop_id           INTEGER NOT NULL REFERENCES stop(stop_id),
    estimated_arrival TEXT,
    calculated_at     TEXT NOT NULL,
    status            TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rejected_update (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bus_id       TEXT,
    reason       TEXT NOT NULL,
    payload      TEXT,
    received_at  TEXT NOT NULL
);
