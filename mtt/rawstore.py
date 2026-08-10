"""Raw store: durable preservation of every source payload.

Every capture writes:
1. raw_events row (jsonb) in Postgres — canonical, queryable
2. filesystem mirror raw/<site>/<YYYY>/<MM>/<DD>/<capture_id>.json
   (gitignored) — human-inspectable audit trail

capture_id is deterministic: sha1(site|endpoint|tournament_ref|captured_at)
so re-running the same tick is a no-op (idempotent).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def capture_id(site: str, endpoint: str, tournament_ref: str, captured_at: str) -> str:
    raw = f"{site}|{endpoint}|{tournament_ref}|{captured_at}"
    return hashlib.sha1(raw.encode()).hexdigest()[:24]


def mirror_path(raw_dir: str, site: str, captured_at: str, cid: str) -> Path:
    dt = datetime.fromisoformat(captured_at)
    return (Path(raw_dir) / site / f"{dt.year:04d}" / f"{dt.month:02d}" / f"{dt.day:02d}"
            / f"{cid}.json")


def save_payload(raw_dir: str, site: str, endpoint: str, tournament_ref: str,
                 captured_at: str, payload: dict) -> str:
    """Save payload to filesystem mirror; returns capture_id."""
    cid = capture_id(site, endpoint, tournament_ref, captured_at)
    path = mirror_path(raw_dir, site, captured_at, cid)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump({"meta": {
            "site": site, "endpoint": endpoint, "tournament_ref": tournament_ref,
            "captured_at": captured_at, "capture_id": cid,
        }, "payload": payload}, f, indent=1, default=str)
    os.replace(tmp, path)
    return cid
