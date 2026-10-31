"""Phase 3: load structured data into PostgreSQL and semi-structured data into MongoDB."""
import pandas as pd
from pymongo import MongoClient
from sqlalchemy import create_engine

from config import DATABASE_URL, MONGO_DB, MONGO_URL


def get_engine():
    return create_engine(DATABASE_URL)


def get_mongo_db():
    return MongoClient(MONGO_URL)[MONGO_DB]


def _clean_for_sql(df: pd.DataFrame) -> pd.DataFrame:
    """Cast nested/object columns (e.g. GeoJSON dicts) to strings so SQL accepts them."""
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == "object":
            out[c] = out[c].astype(str)
    return out


def load_postgres(tables: dict, engine) -> None:
    """Crashes, traffic volume and bike routes: tabular data for SQL joins and aggregates."""
    for df, name in [(tables["crashes"], "crashes"),
                     (tables["traffic"], "traffic_volume"),
                     (tables["bike_routes"], "bike_routes")]:
        _clean_for_sql(df).to_sql(name, engine, if_exists="replace", index=False, chunksize=50_000)
    print("  PostgreSQL updated")


def _mongo_load(db, df: pd.DataFrame, name: str) -> None:
    col = db[name]
    col.delete_many({})
    if df.empty:
        return
    # MongoDB can't store NaN, so convert missing values to None
    df_safe = df.astype(object).where(pd.notnull(df), None)
    col.insert_many(df_safe.to_dict("records"))
    # Indexes for fast bounding-box and street-name lookups
    if {"latitude", "longitude"} <= set(df.columns):
        col.create_index([("latitude", 1), ("longitude", 1)])
    if "std_street" in df.columns:
        col.create_index("std_street")


def load_mongo(tables: dict, db) -> None:
    """Construction permits, 311 lighting complaints and crime: varied fields, geo queries."""
    _mongo_load(db, tables["construction"], "construction_permits")
    _mongo_load(db, tables["lights"], "lighting_complaints")
    _mongo_load(db, tables["crime"], "crime_complaints")
    print("  MongoDB updated")


def load_all(tables: dict) -> None:
    print("PHASE 3: LOAD")
    load_postgres(tables, get_engine())
    load_mongo(tables, get_mongo_db())
