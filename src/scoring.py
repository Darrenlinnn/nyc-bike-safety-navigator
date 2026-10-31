"""Phase 4: geocode, route, and score every street on a bike route (A+ to F)."""
import requests
from sqlalchemy import text

from config import (BIKE_LANE_DISCOUNT, DEFAULT_TRAFFIC, GEO_BOX_DEG,
                    HIGH_TRAFFIC_DISCOUNT, HIGH_TRAFFIC_THRESHOLD, MAX_PENALTY,
                    MIN_SCORE, WEIGHTS)
from transform import standard_street

GRADE_CUTOFFS = [(98, "A+"), (93, "A"), (90, "A-"), (87, "B+"), (83, "B"), (80, "B-"),
                 (77, "C+"), (73, "C"), (70, "C-"), (60, "D")]


def get_grade_letter(score: float) -> str:
    for cutoff, grade in GRADE_CUTOFFS:
        if score >= cutoff:
            return grade
    return "F"


# ---------------------------------------------------------------------------
# External services: OpenStreetMap geocoding + OSRM routing
# ---------------------------------------------------------------------------
def get_lat_lon(address: str):
    """Turn an address or landmark into (lat, lon) with OpenStreetMap Nominatim."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{address}, New York, NY", "format": "json", "limit": 1},
            headers={"User-Agent": "NYCBikeApp"},
            timeout=10,
        )
        d = r.json()
        if d:
            return float(d[0]["lat"]), float(d[0]["lon"])
    except Exception:
        pass
    return None, None


def get_route_path(lat1, lon1, lat2, lon2):
    """Get the route line (GeoJSON) and the ordered list of streets from OSRM."""
    try:
        r = requests.get(
            f"http://router.project-osrm.org/route/v1/driving/"
            f"{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson&steps=true",
            timeout=15,
        )
        d = r.json()
        if "routes" in d:
            geo = d["routes"][0]["geometry"]
            streets = []
            for leg in d["routes"][0]["legs"]:
                for step in leg["steps"]:
                    name = step.get("name", "")
                    dist = step.get("distance", 0)
                    loc = step.get("maneuver", {}).get("location", [0, 0])
                    if not name:
                        continue
                    # Merge consecutive steps on the same street
                    if streets and streets[-1]["name"] == name:
                        streets[-1]["distance"] += dist
                    else:
                        streets.append({"name": name, "distance": dist, "lat": loc[1], "lon": loc[0]})
            return geo, streets
    except Exception:
        pass
    return None, []


# ---------------------------------------------------------------------------
# Street scoring
# ---------------------------------------------------------------------------
def _scalar(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).fetchone()


def score_street(street_name, distance_meters, lat, lon, engine, db):
    """Score one street from 100 (safe) down to 20 (dangerous).

    PostgreSQL: bike lane presence, crashes, injuries, fatalities, traffic volume.
    MongoDB:    bad lighting, crime and construction within ~200 m.
    """
    clean = standard_street(street_name)
    rpt = {"crashes": 0, "injuries": 0, "fatalities": 0, "traffic": 0,
           "const": 0, "lights": 0, "crime": 0, "has_bike_lane": False}

    # Bike lane presence (PostgreSQL)
    try:
        row = _scalar(engine, "SELECT COUNT(*) FROM bike_routes WHERE std_street = :s", s=clean)
        rpt["has_bike_lane"] = (row[0] or 0) > 0
    except Exception:
        pass

    # Crash history + traffic exposure (PostgreSQL)
    try:
        row = _scalar(engine,
                      "SELECT COUNT(*), "
                      "SUM(CAST(number_of_cyclist_injured AS FLOAT)), "
                      "SUM(CAST(number_of_cyclist_killed AS FLOAT)) "
                      "FROM crashes WHERE std_street = :s", s=clean)
        rpt["crashes"], rpt["injuries"], rpt["fatalities"] = (float(v or 0) for v in row)
        row = _scalar(engine, "SELECT AVG(CAST(vol AS FLOAT)) FROM traffic_volume WHERE std_street = :s", s=clean)
        rpt["traffic"] = float(row[0] or 0)
    except Exception:
        pass

    # Nearby environmental hazards (MongoDB bounding-box + text queries)
    try:
        box = {"latitude": {"$gte": lat - GEO_BOX_DEG, "$lte": lat + GEO_BOX_DEG},
               "longitude": {"$gte": lon - GEO_BOX_DEG, "$lte": lon + GEO_BOX_DEG}}
        rpt["lights"] = float(db.lighting_complaints.count_documents(box))
        rpt["crime"] = float(db.crime_complaints.count_documents(box))
        # Construction: some permits have coordinates, others only a street name
        geo_const = float(db.construction_permits.count_documents(box))
        txt_const = float(db.construction_permits.count_documents({"std_street": clean})) if clean else 0.0
        rpt["const"] = max(geo_const, txt_const)
    except Exception:
        pass

    if rpt["traffic"] == 0:
        rpt["traffic"] = DEFAULT_TRAFFIC

    # Normalize crashes by length so long streets aren't unfairly punished
    dist_km = max(distance_meters / 1000, 0.1)
    p_crash = min(rpt["crashes"] / dist_km * WEIGHTS["crash"] * 0.5, MAX_PENALTY["crash"])
    p_other = (rpt["injuries"] * WEIGHTS["injury"]
               + rpt["fatalities"] * WEIGHTS["fatality"]
               + min(rpt["lights"] * WEIGHTS["bad_light"], MAX_PENALTY["bad_light"])
               + min(rpt["crime"] * WEIGHTS["crime"], MAX_PENALTY["crime"])
               + min(rpt["const"] * WEIGHTS["construction"], MAX_PENALTY["construction"]))

    penalty = p_crash + p_other
    if rpt["traffic"] > HIGH_TRAFFIC_THRESHOLD:
        penalty *= HIGH_TRAFFIC_DISCOUNT   # busy streets: crashes partly reflect exposure
    if rpt["has_bike_lane"]:
        penalty *= BIKE_LANE_DISCOUNT      # protective infrastructure bonus

    return int(max(MIN_SCORE, 100 - penalty)), rpt


# ---------------------------------------------------------------------------
# Route analysis
# ---------------------------------------------------------------------------
def _points_sql(engine, table, lat, lon, span=0.05, limit=3000):
    """Random sample of crash points near the route for the map layer."""
    try:
        sql = (f"SELECT CAST(latitude AS FLOAT), CAST(longitude AS FLOAT) FROM {table} "
               "WHERE CAST(latitude AS FLOAT) BETWEEN :la1 AND :la2 "
               "AND CAST(longitude AS FLOAT) BETWEEN :lo1 AND :lo2 "
               "ORDER BY RANDOM() LIMIT :n")
        with engine.connect() as conn:
            rows = conn.execute(text(sql), {"la1": lat - span, "la2": lat + span,
                                            "lo1": lon - span, "lo2": lon + span, "n": limit})
            return [{"lat": r[0], "lon": r[1]} for r in rows]
    except Exception:
        return []


def _points_mongo(db, coll, lat, lon, span=0.05, size=3000):
    try:
        return list(db[coll].aggregate([
            {"$match": {"latitude": {"$gte": lat - span, "$lte": lat + span},
                        "longitude": {"$gte": lon - span, "$lte": lon + span}}},
            {"$sample": {"size": size}},
            {"$project": {"latitude": 1, "longitude": 1, "_id": 0}},
        ]))
    except Exception:
        return []


def analyze_route(start_loc, end_loc, engine, db):
    """Geocode -> route -> score each street -> distance-weighted route grade."""
    lat1, lon1 = get_lat_lon(start_loc)
    lat2, lon2 = get_lat_lon(end_loc)
    if lat1 is None or lat2 is None:
        return {"error": "Address not found."}

    geo, street_list = get_route_path(lat1, lon1, lat2, lon2)
    if not geo:
        return {"error": "Route failed."}

    mid_lat, mid_lon = (lat1 + lat2) / 2, (lon1 + lon2) / 2
    map_data = {
        "crashes": _points_sql(engine, "crashes", mid_lat, mid_lon),
        "lights": _points_mongo(db, "lighting_complaints", mid_lat, mid_lon),
        "crime": _points_mongo(db, "crime_complaints", mid_lat, mid_lon),
        "construction": _points_mongo(db, "construction_permits", mid_lat, mid_lon),
    }

    total_w_score, total_dist = 0.0, 0.0
    details, warnings = [], []
    for item in street_list:
        score, rpt = score_street(item["name"], item["distance"], item["lat"], item["lon"], engine, db)
        # Longer streets count more toward the overall route grade
        total_w_score += score * item["distance"]
        total_dist += item["distance"]
        if score < 60:
            warnings.append(f"{item['name']}: Score {score}")
        details.append({
            "name": item["name"],
            "score": score,
            "grade": get_grade_letter(score),
            "lane": "✅" if rpt["has_bike_lane"] else "❌",
            "stats": f"💥{int(rpt['crashes'])} 👮{int(rpt['crime'])} 🚧{int(rpt['const'])} 💡{int(rpt['lights'])}",
            "dist": f"{int(item['distance'])}m",
            "lat": item["lat"],
            "lon": item["lon"],
        })

    final_score = int(total_w_score / max(1, total_dist))
    return {"start": start_loc, "end": end_loc, "score": final_score,
            "grade": get_grade_letter(final_score), "geo": geo, "map_data": map_data,
            "warnings": warnings, "streets": details}
