"""Provenance Guard — main Flask application.

POST /submit  — run both signals, score, write an audit entry, return JSON.
POST /appeal  — record a creator appeal and mark the original entry under review.
GET  /log     — return recent audit log entries.

Signal 1 is the LLM classifier; Signal 2 is stylometric heuristics; the two are
combined 60/40. /submit is rate limited; /appeal and /log are not.
"""

import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from audit_log import append_entry, get_log, update_entry_status
from signals import compute_confidence, llm_signal, stylometric_signal

load_dotenv()

app = Flask(__name__)
# Render emojis in labels as UTF-8 rather than \uXXXX escapes.
app.json.ensure_ascii = False

# In-memory storage is fine for the MVP; limits are applied per-route below.
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri="memory://",
)


def _now_iso() -> str:
    """Current UTC time as an ISO 8601 string ending in Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
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


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json(silent=True) or {}
    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning")

    if not content_id or not creator_reasoning:
        return (
            jsonify({"error": "Both 'content_id' and 'creator_reasoning' are required."}),
            400,
        )

    # Mark the original classification as under review; None means no such id.
    original = update_entry_status(content_id, "under_review")
    if original is None:
        return jsonify({"error": "content_id not found"}), 404

    append_entry(
        {
            "timestamp": _now_iso(),
            "content_id": content_id,
            "creator_id": original.get("creator_id"),
            "status": "appeal_received",
            "appeal_reasoning": creator_reasoning,
        }
    )

    return jsonify(
        {
            "status": "appeal_received",
            "content_id": content_id,
            "review_status": "under_review",
        }
    )


@app.route("/log", methods=["GET"])
def log():
    return jsonify({"entries": get_log()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
