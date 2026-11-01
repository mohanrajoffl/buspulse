"""Configuration. Every value can be overridden with an environment variable.

Numeric values are DESIGN TARGETS (see report Table 3.2), not measured results.
"""
import os

DB_PATH = os.getenv("BUSPULSE_DB", "buspulse.db")
OPERATOR_KEY = os.getenv("BUSPULSE_OPERATOR_KEY", "dev-operator-key")  # change in production!
AUTO_SEED = os.getenv("BUSPULSE_AUTO_SEED", "1") == "1"
CORS_ORIGINS = os.getenv("BUSPULSE_CORS_ORIGINS", "*").split(",")

STALE_LIMIT_S = int(os.getenv("BUSPULSE_STALE_LIMIT_S", "60"))      # report: e.g. 60 s
V_MIN_KMH = float(os.getenv("BUSPULSE_V_MIN_KMH", "5"))             # plausible bus speed bounds
V_MAX_KMH = float(os.getenv("BUSPULSE_V_MAX_KMH", "60"))
DEFAULT_SPEED_KMH = float(os.getenv("BUSPULSE_DEFAULT_SPEED_KMH", "20"))
EMA_ALPHA = float(os.getenv("BUSPULSE_EMA_ALPHA", "0.4"))            # exponential moving average

T1_MIN = float(os.getenv("BUSPULSE_T1_MIN", "3"))    # < T1 on time
T2_MIN = float(os.getenv("BUSPULSE_T2_MIN", "10"))   # T1..T2 slight delay, > T2 delayed

MAX_PLAUSIBLE_KMH = float(os.getenv("BUSPULSE_MAX_PLAUSIBLE_KMH", "120"))  # position-jump check
CLOCK_TOLERANCE_S = int(os.getenv("BUSPULSE_CLOCK_TOLERANCE_S", "30"))
