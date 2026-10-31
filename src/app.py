"""Phase 5: Flask web app with a Leaflet map.

Usage (after running src/pipeline.py):
    python src/app.py   ->  http://127.0.0.1:5333
"""
import os

from flask import Flask, render_template, request

from load import get_engine, get_mongo_db
from scoring import analyze_route

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))
engine = get_engine()
db = get_mongo_db()


@app.route("/", methods=["GET", "POST"])
def home():
    res, err, s, e = None, None, "", ""
    if request.method == "POST":
        s, e = request.form.get("start", ""), request.form.get("end", "")
        if s and e:
            try:
                res = analyze_route(s, e, engine, db)
                if "error" in res:
                    err = res["error"]
            except Exception as ex:
                err = f"Something went wrong: {ex}"
    return render_template("index.html", r=res, error=err, s=s, e=e)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5333))
    print(f"APP READY: http://127.0.0.1:{port}")
    app.run(port=port, debug=os.getenv("FLASK_DEBUG") == "1")
