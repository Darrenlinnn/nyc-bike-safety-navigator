"""Run the full ETL pipeline: NYC Open Data -> clean -> PostgreSQL + MongoDB.

Usage:
    python src/pipeline.py
"""
from extract import extract_all
from load import load_all
from transform import transform_all


def main():
    raw = extract_all()
    tables = transform_all(raw)
    for name, df in tables.items():
        print(f"  {name:<13} {len(df):>10,} rows")
    load_all(tables)
    print("Pipeline complete. Start the app with: python src/app.py")


if __name__ == "__main__":
    main()
