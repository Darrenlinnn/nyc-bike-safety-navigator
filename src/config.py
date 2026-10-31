"""Shared configuration: data sources, scoring weights and database connections."""
import os

# ---------------------------------------------------------------------------
# Data extraction (NYC Open Data, Socrata SODA API)
# ---------------------------------------------------------------------------
CACHE_DIR = os.getenv("CACHE_DIR", "nyc_data_geo_BIG")
DATE_CUTOFF = "2020-01-01T00:00:00"   # only keep 2020+ records
PAGE_SIZE = 50_000                    # SODA API max rows per request

# How many rows to pull per dataset
TARGET_ROWS = {
    "crashes":       900_000,
    "traffic":       400_000,
    "construction":  1_300_000,
    "street_lights": 1_200_000,
    "bike_routes":   40_000,     # small dataset
    "crime":         1_300_000,
}

# Socrata dataset IDs + server-side filters
DATASETS = {
    "crashes":       {"id": "h9gi-nx95", "where": f"crash_date >= '{DATE_CUTOFF}'"},
    "traffic":       {"id": "7ym2-wayt", "where": "yr >= 2020"},
    "construction":  {"id": "tqtj-sjs8", "where": f"permitissuedate >= '{DATE_CUTOFF}'"},
    "street_lights": {"id": "erm2-nwe9", "where": (
        "(complaint_type='Traffic Signal Condition' OR "
        "complaint_type='Street Light Condition') AND "
        f"created_date >= '{DATE_CUTOFF}'")},
    "bike_routes":   {"id": "mzxg-pwib", "where": "1=1"},
    "crime":         {"id": "qgea-i56i", "where": f"cmplnt_fr_dt >= '{DATE_CUTOFF}'"},
}

# ---------------------------------------------------------------------------
# Databases (override with environment variables, see .env.example)
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/bike_safety_db")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "bike_safety_mongo")

# ---------------------------------------------------------------------------
# Safety scoring
# ---------------------------------------------------------------------------
WEIGHTS = {
    "crash": 4,
    "injury": 10,
    "fatality": 30,
    "construction": 3,
    "bad_light": 3,
    "crime": 2,
}
MAX_PENALTY = {"crash": 40, "bad_light": 10, "crime": 20, "construction": 10}
BIKE_LANE_DISCOUNT = 0.7        # bike lane present -> penalty x 0.7
HIGH_TRAFFIC_THRESHOLD = 20_000 # busy streets: crashes partly reflect exposure
HIGH_TRAFFIC_DISCOUNT = 0.6
DEFAULT_TRAFFIC = 15_000.0      # used when a street has no traffic counts
GEO_BOX_DEG = 0.002             # ~200 m search box for lights/crime/construction
MIN_SCORE = 20
