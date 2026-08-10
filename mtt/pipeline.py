"""Pipeline orchestration for one ingestion run.

Flow per run (site):
    run record (ingestion_runs)
      -> adapter.discover()          raw -> tournaments (classify + quality)
      -> per active tournament: adapter.snapshot() -> raw -> snapshots
      -> per tournament: adapter.results() -> raw -> players/player_tournaments
      -> parser errors logged
      -> run completed with counters

Idempotency: unique constraints + deterministic capture ids make a second
run a no-op for identical captures (duplicates counter tracks skips).
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from . import PARSER_VERSION, DEFAULT_RAW_DIR, classifier, db, normalize, quality, rawstore


def _captured_at():
    return datetime.now(timezone.utc).isoformat()


def ingest(conn, adapter, run_id: Optional[str] = None,
           raw_dir: str = DEFAULT_RAW_DIR, snapshot_live: bool = True,
           capture_results: bool = True) -> dict:
    """Run one ingest tick for a site adapter. Returns counters dict."""
    site = adapter.site
    run_id = run_id or f"{site}-{uuid.uuid4().hex[:12]}"
    started = time.monotonic()
    counters: dict = dict(discovered=0, captured=0, failed=0, players=0, hands=0,
                          duplicates=0, validation_errors=0, status="running",
                          duration_s=0.0)
    db.start_run(conn, run_id, site)

    try:
        raw_tournaments = adapter.discover()
        counters["discovered"] = len(raw_tournaments)

        for rt in raw_tournaments:
            ref = str(rt.get("site_tournament_id") or rt.get("name") or "?")
            try:
                counters["captured"] += _ingest_tournament(
                    conn, adapter, rt, run_id, site, raw_dir, counters,
                    snapshot_live, capture_results)
            except Exception as e:  # one bad tournament must not kill the run
                db.log_parser_error(conn, run_id, site, ref, "PARSER_ERROR", str(e))
                counters["failed"] += 1
                counters["validation_errors"] += 1

        counters["status"] = "completed"
    except Exception as e:
        counters["status"] = "failed"
        db.log_parser_error(conn, run_id, site, "*", "RUN_ERROR", str(e))
    finally:
        counters["duration_s"] = round(time.monotonic() - started, 2)
        db.complete_run(conn, run_id, counters)
    return counters


def _ingest_tournament(conn, adapter, rt, run_id, site, raw_dir, counters,
                       snapshot_live, capture_results) -> int:
    captured_at = _captured_at()
    ref = str(rt.get("site_tournament_id") or rt.get("name") or "?")

    # 1. raw first — never parse without preserving the source
    cid = rawstore.save_payload(raw_dir, site, "discover", ref, captured_at, rt)
    outcome = db.insert_raw_event(conn, site, cid, ref, "discover", captured_at,
                                  PARSER_VERSION, rt)
    if outcome == "duplicate":
        counters["duplicates"] += 1

    # 2. normalize + classify + quality
    t = normalize.normalize_tournament(rt)
    if t["site"] is None:
        t["site"] = site
    classifier.classify_tournament(t)
    score, flags = quality.score_tournament(t)

    # 3. idempotent upsert
    db.upsert_tournament(conn, t, score, flags)
    conn.commit()

    tournament_pk = db.tournament_id(conn, site, t["site_tournament_id"])
    if tournament_pk is None:
        raise RuntimeError(f"tournament not persisted: {site}/{t['site_tournament_id']}")

    # 4. lifecycle snapshots
    if snapshot_live:
        snap = adapter.snapshot(ref)
        if snap:
            snap["captured_at"] = snap.get("captured_at") or captured_at
            ns = normalize.normalize_snapshot(snap)
            s_cid = rawstore.save_payload(raw_dir, site, "snapshot", ref,
                                          ns["captured_at"], snap)
            if db.insert_raw_event(conn, site, s_cid, ref, "snapshot",
                                   ns["captured_at"], PARSER_VERSION, snap) == "duplicate":
                counters["duplicates"] += 1
            db.upsert_snapshot(conn, tournament_pk, ns, raw_payload=snap)
            conn.commit()

    # 5. results -> players
    if capture_results:
        res = adapter.results(ref)
        if res:
            r_cid = rawstore.save_payload(raw_dir, site, "results", ref,
                                          captured_at, res)
            if db.insert_raw_event(conn, site, r_cid, ref, "results", captured_at,
                                   PARSER_VERSION, res) == "duplicate":
                counters["duplicates"] += 1
            for pr in res.get("players", []) or []:
                p = normalize.normalize_player({**pr, "site": site})
                if not p["display_name"]:
                    continue
                pid = db.upsert_player(conn, site, p["display_name"],
                                       site_player_id=p.get("site_player_id"),
                                       normalized_name=p.get("normalized_name"))
                db.upsert_player_tournament(conn, pid, tournament_pk, p)
                counters["players"] += 1
            if res.get("final_status"):
                db.query(conn,
                         f"UPDATE {db.schema_name()}.tournaments SET status=%s WHERE id=%s",
                         (normalize.normalize_status(res["final_status"]), tournament_pk))
            conn.commit()
    return 1
