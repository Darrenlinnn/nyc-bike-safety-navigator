"""Phase 2: clean coordinates and standardize street names across datasets."""
import pandas as pd

# Common abbreviations so "West 43rd Street" and "W 43 St" can match
STREET_REPLACEMENTS = {
    " AVENUE": " AVE",
    " STREET": " ST",
    " ROAD": " RD",
    " BOULEVARD": " BLVD",
    " PLACE": " PL",
    " EAST ": " E ",
    " WEST ": " W ",
    " NORTH ": " N ",
    " SOUTH ": " S ",
}


def standard_street(name):
    """Normalize a street name to one format, e.g. 'West 42nd Street' -> 'WEST 42ND ST'."""
    if not isinstance(name, str) or name == "nan":
        return None
    clean = name.upper().strip()
    for old, new in STREET_REPLACEMENTS.items():
        clean = clean.replace(old, new)
    return clean.strip()


def fix_coords(df: pd.DataFrame) -> pd.DataFrame:
    """Make latitude/longitude numeric and drop rows without valid coordinates."""
    if df.empty or not {"latitude", "longitude"} <= set(df.columns):
        return pd.DataFrame()
    df = df.copy()
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    return df.dropna(subset=["latitude", "longitude"])


def _add_std_street(df: pd.DataFrame, candidates) -> pd.DataFrame:
    """Add a `std_street` column from the first street-name column that exists."""
    for col in candidates:
        if col in df.columns:
            df = df.copy()
            df["std_street"] = df[col].apply(standard_street)
            break
    return df


def transform_all(raw: dict) -> dict:
    """Clean every dataset and return the tables ready for loading."""
    print("PHASE 2: TRANSFORM")
    crashes = _add_std_street(fix_coords(raw["crashes"]), ["on_street_name"])
    lights = fix_coords(raw["street_lights"])
    crime = fix_coords(raw["crime"])

    traffic = raw["traffic"].copy()
    if not traffic.empty:
        traffic["vol"] = pd.to_numeric(traffic["vol"], errors="coerce").fillna(0)
        traffic = _add_std_street(traffic, ["street"])

    routes = _add_std_street(raw["bike_routes"], ["street", "tf_facilit"])

    # Construction permits often lack coordinates, so keep every row and
    # rely on the street-name text match as a fallback during scoring
    construction = _add_std_street(raw["construction"], ["onstreetname", "on_street_name"])
    if "latitude" in construction.columns:
        construction = fix_coords(construction)

    return {
        "crashes": crashes, "traffic": traffic, "bike_routes": routes,
        "construction": construction, "lights": lights, "crime": crime,
    }
