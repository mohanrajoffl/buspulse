"""Demo data. Coordinates are ILLUSTRATIVE (a straight line near Salem, ~1.17 km per
segment, like report Table 4.3) - replace with surveyed stop coordinates."""
import sqlite3

from .timeutil import iso, utcnow

R12 = [
    ("New Bus Stand", 11.6745, 78.1548, 0),
    ("Five Roads", 11.6745, 78.1655, 3),
    ("Hasthampatti", 11.6745, 78.1762, 6),
    ("Fairlands", 11.6745, 78.1869, 9),
    ("College stop", 11.6745, 78.1976, 12),
]
R07 = [
    ("Old Bus Stand", 11.6900, 78.1500, 0),
    ("Five Roads", 11.6745, 78.1655, 6),
    ("Collectorate", 11.6600, 78.1800, 12),
]


def seed(conn: sqlite3.Connection) -> bool:
    if conn.execute("SELECT COUNT(*) FROM route").fetchone()[0]:
        return False
    for name, start, end, stops in (("R12", "New Bus Stand", "College stop", R12), ("R07", "Old Bus Stand", "Collectorate", R07)):
        rid = conn.execute("INSERT INTO route (route_name,start_point,end_point) VALUES (?,?,?)", (name, start, end)).lastrowid
        for seq, (sname, lat, lon, off) in enumerate(stops, start=1):
            conn.execute(
                "INSERT INTO stop (route_id,stop_name,latitude,longitude,sequence_number,scheduled_offset_min) VALUES (?,?,?,?,?,?)",
                (rid, sname, lat, lon, seq, off),
            )
    now = iso(utcnow())
    buses = [("TN30-1234", "TN30-1234", 1, now), ("TN30-5678", "TN30-5678", 1, now), ("TN30-7777", "TN30-7777", 2, now)]
    conn.executemany("INSERT INTO bus (bus_id,registration,route_id,trip_start) VALUES (?,?,?,?)", buses)
    conn.commit()
    return True


if __name__ == "__main__":
    from .db import get_conn, init_db

    init_db()
    c = get_conn()
    print("seeded" if seed(c) else "already has data")
