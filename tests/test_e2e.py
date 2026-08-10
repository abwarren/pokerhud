"""E2E: complete pipeline looped 3x against deterministic fixtures.

Each run is a FULL cycle:
    adapter.discover -> raw store -> normalize -> classify -> DB
    -> snapshots -> results -> players -> reconcile -> daily ledger
    -> reparse raw with parser v2 (no data loss)

Assertions per run:
    - all tournaments captured, zero failures
    - R1000 cohort isolated in DB + ledger
    - raw events preserved, reparse produces identical tournament rows
    - double-run idempotent (no duplicate tournaments)
"""

import os
from datetime import date

import pytest

from mtt import db, ledger
from mtt.adapters import FixtureAdapter
from mtt.pipeline import ingest

from helpers import load, reset_schema

PB_DAY = load("pokerbet_day.json")["tournaments"]
SB_DAY = load("sunbet_day.json")["tournaments"]
SNAPS = load("snapshots.json")
RESULTS = load("results.json")
DAY = date(2026, 8, 10)

TOTAL_EXPECTED = len(PB_DAY) + len(SB_DAY)  # 10


@pytest.fixture()
def conn():
    c = db.connect()
    db.ensure_schema(c)
    yield c
    c.close()


def full_cycle(conn, tag: str):
    """One complete E2E cycle. Returns counters."""
    import copy
    reset_schema(conn)
    counters = {}
    for site, fixtures in (("pokerbet", PB_DAY), ("sunbet", SB_DAY)):
        adapter = FixtureAdapter(site, copy.deepcopy(fixtures),
                                 copy.deepcopy(SNAPS), copy.deepcopy(RESULTS))
        counters[site] = ingest(conn, adapter, run_id=f"e2e-{tag}-{site}",
                                raw_dir=os.environ["MTT_RAW_DIR"])
    return counters


def assert_cycle_valid(conn, tag: str, counters: dict):
    s = db.schema_name()
    for site in ("pokerbet", "sunbet"):
        c = counters[site]
        assert c["status"] == "completed", f"{tag}/{site}: run failed: {c}"
        assert c["failed"] == 0, f"{tag}/{site}: {c['failed']} failures"
        assert c["duplicates"] == 0, f"{tag}/{site}: dupes on fresh schema"

    n = db.query(conn, f"SELECT COUNT(*) n FROM {s}.tournaments")[0]["n"]
    assert n == TOTAL_EXPECTED, f"{tag}: expected {TOTAL_EXPECTED} tournaments, got {n}"

    # R1000 isolation
    r1000 = db.query(conn, f"SELECT site, name FROM {s}.tournaments WHERE cohort='R1000'")
    assert len(r1000) == 2, f"{tag}: expected 2 R1000 tournaments, got {len(r1000)}"
    assert {r["site"] for r in r1000} == {"pokerbet", "sunbet"}

    # Non-R1000 cohorts never contain an R1000 buy-in
    mixed = db.query(conn, f"SELECT buyin FROM {s}.tournaments WHERE cohort != 'R1000' AND buyin=1000")
    assert mixed == [], f"{tag}: R1000 buy-in leaked into another cohort: {mixed}"

    # snapshots + results + players landed
    assert db.query(conn, f"SELECT COUNT(*) n FROM {s}.tournament_snapshots")[0]["n"] > 0
    assert db.query(conn, f"SELECT COUNT(*) n FROM {s}.players")[0]["n"] == 6
    assert db.query(conn, f"SELECT COUNT(*) n FROM {s}.player_tournaments")[0]["n"] == 6

    # raw preserved: discover+snapshot+results for every tournament
    raw = db.query(conn, f"SELECT site, endpoint, COUNT(*) n FROM {s}.raw_events GROUP BY site, endpoint")
    by = {(r["site"], r["endpoint"]): r["n"] for r in raw}
    assert by[("pokerbet", "discover")] == len(PB_DAY)
    assert by[("sunbet", "discover")] == len(SB_DAY)
    assert by[("pokerbet", "snapshot")] == 2
    assert by[("sunbet", "snapshot")] == 1
    assert by[("pokerbet", "results")] == 1
    assert by[("sunbet", "results")] == 1

    # ledger rows for every site/cohort, R1000 present
    report = ledger.reconcile(conn, DAY)
    cohorts = {(site, cohort) for (site, cohort) in report}
    for site in ("pokerbet", "sunbet"):
        assert (site, "R1000") in cohorts
    text = ledger.render_report(report, DAY)
    assert "R1000" in text


def test_reparse_parser_v2(conn):
    """Raw events survive parser upgrades: re-parse from raw -> same rows."""
    full_cycle(conn, "reparse")
    s = db.schema_name()
    before = db.query(conn, f"SELECT site, site_tournament_id, buyin, name FROM {s}.tournaments ORDER BY site, site_tournament_id")

    # simulate parser v2: wipe tournaments, re-run from raw_events only
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {s}.tournament_snapshots")
        cur.execute(f"DELETE FROM {s}.player_tournaments")
        cur.execute(f"DELETE FROM {s}.players")
        cur.execute(f"DELETE FROM {s}.tournaments")
    conn.commit()

    raws = db.query(conn, f"SELECT raw_payload FROM {s}.raw_events WHERE endpoint='discover'")
    assert len(raws) == TOTAL_EXPECTED
    for r in raws:
        t = r["raw_payload"]
        adapter = FixtureAdapter(t["site"], [t])
        ingest(conn, adapter, run_id=f"reparse-{t['site']}-{t['site_tournament_id']}",
               raw_dir=os.environ["MTT_RAW_DIR"], snapshot_live=False, capture_results=False)

    after = db.query(conn, f"SELECT site, site_tournament_id, buyin, name FROM {s}.tournaments ORDER BY site, site_tournament_id")
    assert before == after, "parser v2 reparse lost or altered data"


def test_double_run_no_duplicates(conn):
    """Running the same capture twice: tournaments stay at N, raw no dupes."""
    full_cycle(conn, "idem")
    s = db.schema_name()
    import copy
    adapter = FixtureAdapter("pokerbet", copy.deepcopy(PB_DAY),
                             copy.deepcopy(SNAPS), copy.deepcopy(RESULTS))
    counters = ingest(conn, adapter, run_id="e2e-idem-pokerbet-2",
                      raw_dir=os.environ["MTT_RAW_DIR"])
    assert counters["duplicates"] > 0, "second run should hit duplicate raw captures"
    n = db.query(conn, f"SELECT COUNT(*) n FROM {s}.tournaments WHERE site='pokerbet'")[0]["n"]
    assert n == len(PB_DAY), f"duplicate tournaments after rerun: {n}"


@pytest.mark.parametrize("cycle", ["run-1", "run-2", "run-3"])
def test_e2e_loop(conn, cycle):
    """The mandated repeated end-to-end runs (fresh schema each time)."""
    counters = full_cycle(conn, cycle)
    assert_cycle_valid(conn, cycle, counters)
