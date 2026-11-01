# Architecture (report Chapter 3)

```
GPS device --(HTTPS POST)--> Backend API + validation --> Database
                                                            |
                                  ETA / delay module <------+
                                        |
                                  Passenger app (map, route, ETA, alerts)      Operator dashboard (planned)
```

Three layers: **Presentation** (React PWA) -> **Application** (FastAPI: validation, route lookup, ETA, stale check) -> **Data** (SQLite; swap for PostgreSQL in production).

## ETA algorithm (`backend/app/eta.py`)
1. `d` = distance bus -> next stop + sum of following segments up to the selected stop (haversine).
2. `v` = exponential moving average of recent speeds, clamped to `[V_MIN, V_MAX]` (default speed flagged as *assumed* when no data).
3. `ETA = now + d / v`; `delay = ETA - scheduled` -> `ON TIME (<3 min)`, `SLIGHT DELAY (3-10)`, `DELAYED (>10)`.
4. Location older than `STALE_LIMIT_S` (60 s) -> **LIVE DATA UNAVAILABLE** (never shown as if current).

## Validation rules (`backend/app/validation.py`)
Known bus, lat in [-90,90], lon in [-180,180], timestamp not in the future (30 s tolerance), newer than previous update, physically plausible jump (<= 120 km/h). Rejected updates are logged in `rejected_update`.

## Test cases -> code (report Table 5.3)
| ID | Where |
|----|-------|
| TC-01..05, 07, 08 | `backend/tests/test_api.py`, `test_eta.py` |
| TC-06 offline | manual: run app, load once, stop backend, reload (cached stops + "Live data unavailable") |

## Roadmap (report 6.3)
Trained ML ETA (gradient boosting / LSTM) once verified trip data exists - must beat the baseline on MAE/RMSE/MAPE; operator dashboard UI; ticketing/QR; Tamil/Hindi; Supabase/PostgreSQL + Realtime; GPS hardware (ESP32/Raspberry Pi + SIM module).
