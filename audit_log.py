"""Minimal audit log writer for Provenance Guard.

Entries are stored as a JSON list in `audit_log.json` at the project root.
SQLite would be the production choice; a single file keeps the MVP simple.
"""

import json
import os

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_log.json")


def get_log() -> list[dict]:
    """Read audit_log.json and return the list of entries.

    Returns an empty list if the file does not exist or is unreadable/corrupt.
    """
    if not os.path.exists(_LOG_PATH):
        return []
    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def append_entry(entry: dict) -> None:
    """Append `entry` to the audit log and write it back, pretty-printed."""
    entries = get_log()
    entries.append(entry)
    _write(entries)


def update_entry_status(content_id: str, new_status: str) -> dict | None:
    """Set the status of the entry matching `content_id`, write back, and return it.

    Returns the updated entry, or None if no entry with that content_id exists.
    Updates the first (original) match — appeal entries share the content_id but
    the classified entry is written first.
    """
    entries = get_log()
    for entry in entries:
        if entry.get("content_id") == content_id and entry.get("status") != "appeal_received":
            entry["status"] = new_status
            _write(entries)
            return entry
    return None


def _write(entries: list[dict]) -> None:
    with open(_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
