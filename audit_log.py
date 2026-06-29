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
    with open(_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
