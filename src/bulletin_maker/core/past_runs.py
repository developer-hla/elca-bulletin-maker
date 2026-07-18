"""Past-run storage — saved wizard form data, one entry per service date.

Stored as JSON in ~/.bulletin-maker/past_runs.json, shared by the
desktop bridge and the web adapter.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_PAST_RUNS = 20


def _path() -> Path:
    return Path.home() / ".bulletin-maker" / "past_runs.json"


def read_past_runs() -> list:
    try:
        path = _path()
        if path.exists():
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return data
    except Exception:
        logger.debug("Could not read past runs", exc_info=True)
    return []


def _write(runs: list) -> None:
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(runs[:MAX_PAST_RUNS], indent=2))
    except Exception:
        logger.debug("Could not write past runs", exc_info=True)


def save_past_run(form_data: dict, metadata: dict) -> str:
    now = datetime.now()
    run = {
        "id": now.strftime("%Y%m%d%H%M%S"),
        "timestamp": now.isoformat(),
        "metadata": metadata,
        "form_data": form_data,
    }
    runs = read_past_runs()
    runs = [r for r in runs
            if r.get("form_data", {}).get("date") != form_data.get("date")]
    runs.insert(0, run)
    _write(runs)
    return run["id"]


def list_past_runs() -> list:
    return [
        {
            "id": r.get("id", ""),
            "timestamp": r.get("timestamp", ""),
            "metadata": r.get("metadata", {}),
            "date": r.get("form_data", {}).get("date", ""),
        }
        for r in read_past_runs()
    ]


def get_past_run(run_id: str) -> Optional[dict]:
    for r in read_past_runs():
        if r.get("id") == run_id:
            return r
    return None


def delete_past_run(run_id: str) -> bool:
    runs = read_past_runs()
    filtered = [r for r in runs if r.get("id") != run_id]
    if len(filtered) == len(runs):
        return False
    _write(filtered)
    return True
