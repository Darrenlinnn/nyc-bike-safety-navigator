"""Phase 1: download NYC Open Data in pages, with a local pickle cache."""
import os
import time
import urllib.parse

import pandas as pd

from config import CACHE_DIR, DATASETS, PAGE_SIZE, TARGET_ROWS


def download_dataset(key: str) -> pd.DataFrame:
    """Download one dataset in 50k-row pages until TARGET_ROWS is reached.

    Results are cached as .pkl so later runs skip the multi-GB download.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{key}.pkl")

    # Reuse cached data when available
    if os.path.exists(cache_path):
        print(f"  {key}: loaded from cache")
        try:
            return pd.read_pickle(cache_path)
        except Exception as e:
            print(f"  cache read failed for {key}: {e}")

    cfg = DATASETS[key]
    print(f"\nDownloading '{key}' (target: {TARGET_ROWS[key]:,} rows) ...")
    base_url = f"https://data.cityofnewyork.us/resource/{cfg['id']}.json"

    offset, total, chunks = 0, 0, []
    while total < TARGET_ROWS[key]:
        params = {"$limit": PAGE_SIZE, "$offset": offset, "$where": cfg["where"]}
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        try:
            chunk = pd.read_json(url)
        except Exception as e:
            print("  API error:", e)
            break
        if chunk.empty:
            print("  API returned no more rows for", key)
            break

        chunks.append(chunk)
        total += len(chunk)
        offset += PAGE_SIZE
        print(f"    {key}: {total:,} rows so far")
        time.sleep(0.2)  # be polite to the API (avoid throttling)

    if not chunks:
        return pd.DataFrame()

    df = pd.concat(chunks, ignore_index=True)
    df.columns = df.columns.str.lower()
    try:
        df.to_pickle(cache_path)
        print(f"  saved {len(df):,} rows for {key}")
    except Exception as e:
        print(f"  failed to save cache for {key}: {e}")
    return df


def extract_all() -> dict:
    """Download (or load from cache) all six datasets."""
    print("PHASE 1: EXTRACT")
    return {key: download_dataset(key) for key in DATASETS}
