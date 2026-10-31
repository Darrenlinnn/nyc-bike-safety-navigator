"""End-to-end test: transform -> load -> score -> Flask, using SQLite + in-memory MongoDB.

Run with:  pytest tests/
"""
import os
import sys

import mongomock
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ["DATABASE_URL"] = "sqlite:///test_bike_safety.db"

import load  # noqa: E402
import scoring  # noqa: E402
from transform import standard_street, transform_all  # noqa: E402

MONGO = mongomock.MongoClient()["bike_safety_test"]
load.get_mongo_db = lambda: MONGO


def fake_raw():
    """Tiny datasets shaped like the real NYC Open Data tables."""
    return {
        "crashes": pd.DataFrame({"latitude": ["40.750", "40.751", "bad"],
                                 "longitude": ["-73.990", "-73.991", "-73.99"],
                                 "on_street_name": ["7th Avenue", "7th Avenue", "Broadway"],
                                 "number_of_cyclist_injured": [1, 0, 1],
                                 "number_of_cyclist_killed": [0, 0, 0]}),
        "traffic": pd.DataFrame({"street": ["7th Avenue"], "vol": ["25000"]}),
        "bike_routes": pd.DataFrame({"street": ["West 32nd Street"]}),
        "construction": pd.DataFrame({"onstreetname": ["7th Avenue"],
                                      "latitude": [40.7505], "longitude": [-73.9905]}),
        "street_lights": pd.DataFrame({"latitude": [40.7501], "longitude": [-73.9901]}),
        "crime": pd.DataFrame({"latitude": [40.7502, None], "longitude": [-73.9902, -73.99]}),
    }


def setup_module():
    tables = transform_all(fake_raw())
    load.load_postgres(tables, load.get_engine())
    load.load_mongo(tables, MONGO)


def teardown_module():
    if os.path.exists("test_bike_safety.db"):
        os.remove("test_bike_safety.db")


def test_standard_street():
    assert standard_street("7th Avenue") == "7TH AVE"
    assert standard_street("West 32nd Street") == "WEST 32ND ST"
    assert standard_street(None) is None


def test_transform_drops_invalid_coordinates():
    tables = transform_all(fake_raw())
    assert len(tables["crashes"]) == 2
    assert len(tables["crime"]) == 1


def test_score_street_combines_sql_and_mongo():
    score, rpt = scoring.score_street("7th Avenue", 937, 40.750, -73.990, load.get_engine(), MONGO)
    assert (rpt["crashes"], rpt["injuries"], rpt["lights"], rpt["crime"], rpt["const"]) == (2, 1, 1, 1, 1)
    # penalty = (2 / 0.937 * 4 * 0.5 + 10 + 3 + 2 + 3) * 0.6 (high traffic) = 13.4
    assert score == 86 and scoring.get_grade_letter(score) == "B"


def test_bike_lane_street_with_no_hazards_scores_100():
    score, rpt = scoring.score_street("West 32nd Street", 276, 40.0, -70.0, load.get_engine(), MONGO)
    assert rpt["has_bike_lane"] and score == 100


def test_grade_cutoffs():
    assert [scoring.get_grade_letter(s) for s in (99, 90, 75, 65, 20)] == ["A+", "A-", "C", "D", "F"]


def test_flask_route_page(monkeypatch):
    monkeypatch.setattr(scoring, "get_lat_lon",
                        lambda a: (40.758, -73.985) if "times" in a else (40.750, -73.988))
    monkeypatch.setattr(scoring, "get_route_path", lambda *a: (
        {"type": "LineString", "coordinates": [[-73.985, 40.758], [-73.988, 40.750]]},
        [{"name": "7th Avenue", "distance": 937, "lat": 40.750, "lon": -73.990}]))
    import app as webapp
    client = webapp.app.test_client()
    assert client.get("/").status_code == 200
    html = client.post("/", data={"start": "times square", "end": "herald square"}).get_data(as_text=True)
    assert "Weighted Safety Score" in html and "7th Avenue" in html
