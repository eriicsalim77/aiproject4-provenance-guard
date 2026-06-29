"""Provenance Guard — main Flask application (Milestone 3 foundation).

POST /submit  — run Signal 1 (LLM), write an audit entry, return structured JSON.
GET  /log     — return recent audit log entries.

Milestone 4 adds Signal 2 (stylometry) and confidence scoring; Milestone 5 adds
labels, appeals, and rate limits. Flask-Limiter is wired up here but no limits
are applied yet.
"""

import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from audit_log import append_entry, get_log
from signals import compute_confidence, llm_signal, stylometric_signal

load_dotenv()

app = Flask(__name__)
# Render emojis in labels as UTF-8 rather than \uXXXX escapes.
app.json.ensure_ascii = False

# Limits are applied in Milestone 5; in-memory storage is fine for the MVP.
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri="memory://",
)


def _now_iso() -> str:
    """Current UTC time as an ISO 8601 string ending in Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "Both 'text' and 'creator_id' are required."}), 400

    content_id = str(uuid.uuid4())
    timestamp = _now_iso()

    # Signal 1 (LLM) and Signal 2 (stylometry), combined 60/40 in compute_confidence.
    llm_score = llm_signal(text)["score"]
    stylometric_score = stylometric_signal(text)["score"]
    scoring = compute_confidence(llm_score, stylometric_score)

    entry = {
        "timestamp": timestamp,
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": scoring["attribution"],
        "confidence": scoring["confidence"],
        "llm_score": llm_score,
        "stylometric_score": stylometric_score,
        "status": "classified",
    }
    append_entry(entry)

    return jsonify(
        {
            "content_id": content_id,
            "attribution": scoring["attribution"],
            "confidence": scoring["confidence"],
            "llm_score": llm_score,
            "stylometric_score": stylometric_score,
            "label": scoring["label"],
            "timestamp": timestamp,
        }
    )


@app.route("/log", methods=["GET"])
def log():
    return jsonify({"entries": get_log()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
