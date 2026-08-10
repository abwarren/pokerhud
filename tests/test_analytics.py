"""Analytics views: cohort-separated datasets, R1000 isolation by design."""

import copy
import os
from datetime import date

import pytest

from mtt import analytics, db
from mtt.adapters import FixtureAdapter
from mtt.ledger import reconcile
from mtt.pipeline import ingest

from helpers import load, reset_schema

PB_DAY = load("pokerbet_day.json")["tournaments"]
SB_DAY = load("sunbet_day.json")["tournaments"]
SNAPS = load("snapshots.json")
RESULTS = load("results.json")
DAY = date(2026, 8, 10)


@pytest.fixture()
def conn():
    c = db.connect()
    db.ensure_schema(c)
    reset_schema(c)
    yield c
    c.close()


def seed(conn):
    for site, fixtures in (("pokerbet", PB_DAY), ("sunbet", SB_DAY)):
        ingest(conn, FixtureAdapter(site, copy.deepcopy(fixtures),
                                    copy.deepcopy(SNAPS), copy.deepcopy(RESULTS)),
               run_id=f"an-{site}", raw_dir=os.environ["MTT_RAW_DIR"])
    reconcile(conn, DAY)


def test_cohort_summary_view(conn):
    seed(conn)
    rows = analytics.cohort_summary(conn)
    keys = {(r["site"], r["cohort"]) for r in rows}
    assert ("pokerbet", "R1000") in keys
    assert ("sunbet", "R1000") in keys
    assert ("pokerbet", "HIGH") in keys
    # every row carries its cohort + field band
    for r in rows:
        assert r["cohort"] and r["field_band"]
    r1000 = [r for r in rows if r["cohort"] == "R1000"]
    assert len(r1000) == 2
    assert sum(r["entries"] for r in r1000) == 87 + 121


def test_player_performance_roi_and_isolation(conn):
    seed(conn)
    rows = analytics.player_performance(conn, cohort="R1000")
    # no R1000 players exist (results only for t-1003/s-2002) -> empty
    assert rows == []
    rows = analytics.player_performance(conn)
    by = {(r["site"], r["display_name"]): r for r in rows}
    ace = by[("pokerbet", "AceOfSpades")]
    assert ace["cohort"] == "SMALL"
    assert ace["tournaments_played"] == 1
    assert ace["cash_count"] == 1
    assert ace["total_prizes"] == 7800
    assert ace["total_cost"] == 220          # buyin 200 + fee 20
    assert ace["net_profit"] == 7580
    assert ace["roi_pct"] > 3000             # (7800/220-1)*100
    # rows keyed by cohort: same player can appear in multiple cohorts,
    # but R1000 rows are always separate
    cohorts_for_ace = [r["cohort"] for r in rows if r["display_name"] == "AceOfSpades"]
    assert cohorts_for_ace == ["SMALL"]


def test_daily_summary_view(conn):
    seed(conn)
    rows = analytics.daily_summary(conn, DAY)
    by = {(r["site"], r["cohort"]): r for r in rows}
    assert by[("pokerbet", "R1000")]["tournaments_expected"] == 1
    assert by[("sunbet", "R1000")]["tournaments_expected"] == 1
    assert by[("pokerbet", "MICRO")]["tournaments_expected"] == 1


def test_export_day_isolates_r1000(conn):
    seed(conn)
    out = analytics.export_day(conn, DAY)
    assert out["date"] == "2026-08-10"
    r1000 = out["r1000"]["tournaments"]
    assert len(r1000) == 2
    for t in r1000:
        assert t["buyin"] == 1000
    # no non-R1000 row in the r1000 block
    assert all(t["cohort"] == "R1000" for t in out["r1000"]["tournaments"])
    # daily rows include both sites' R1000
    daily = {(r["site"], r["cohort"]) for r in out["daily"]}
    assert ("pokerbet", "R1000") in daily and ("sunbet", "R1000") in daily
