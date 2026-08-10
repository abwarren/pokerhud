"""tournament_cohorts: explicit assignments + reclassification history."""

import copy
import os

import pytest

from mtt import db
from mtt.adapters import FixtureAdapter
from mtt.pipeline import ingest

from helpers import load, reset_schema

PB_DAY = load("pokerbet_day.json")["tournaments"]
SNAPS = load("snapshots.json")
RESULTS = load("results.json")


@pytest.fixture()
def conn():
    c = db.connect()
    db.ensure_schema(c)
    reset_schema(c)
    yield c
    c.close()


def test_cohort_rows_written(conn):
    adapter = FixtureAdapter("pokerbet", copy.deepcopy(PB_DAY),
                             copy.deepcopy(SNAPS), copy.deepcopy(RESULTS))
    ingest(conn, adapter, run_id="coh-1", raw_dir=os.environ["MTT_RAW_DIR"])
    s = db.schema_name()
    rows = db.query(conn, f"SELECT cohort, COUNT(*) n FROM {s}.tournament_cohorts "
                          f"GROUP BY cohort ORDER BY cohort")
    by = {r["cohort"]: r["n"] for r in rows}
    assert by["R1000"] == 1
    assert by["SMALL"] == 2
    assert by["MID"] == 1
    assert by["HIGH"] == 1
    assert by["MICRO"] == 1
    # every classified tournament has exactly one assignment row
    assert sum(by.values()) == 6


def test_reclassification_keeps_history(conn):
    # t-1002 starts with a R125k guarantee (MID); a corrected source says
    # the guarantee is R1,000 -> the tournament moves into the R1000 cohort
    day = copy.deepcopy(PB_DAY)
    t1002 = next(t for t in day if t["site_tournament_id"] == "t-1002")
    t1002["guarantee"] = 125000
    ingest(conn, FixtureAdapter("pokerbet", day, {}, {}), run_id="coh-2a",
           raw_dir=os.environ["MTT_RAW_DIR"])
    t1002["guarantee"] = 1000
    ingest(conn, FixtureAdapter("pokerbet", day, {}, {}), run_id="coh-2b",
           raw_dir=os.environ["MTT_RAW_DIR"])
    s = db.schema_name()
    rows = db.query(conn,
                    f"SELECT tc.cohort FROM {s}.tournament_cohorts tc "
                    f"JOIN {s}.tournaments t ON t.id = tc.tournament_id "
                    "WHERE t.site_tournament_id='t-1002' ORDER BY tc.assigned_at")
    cohorts = [r["cohort"] for r in rows]
    assert "MID" in cohorts and "R1000" in cohorts  # both assignments preserved
    # current assignment on the tournament row is R1000
    cur = db.query(conn, f"SELECT cohort FROM {s}.tournaments "
                         "WHERE site_tournament_id='t-1002'")[0]
    assert cur["cohort"] == "R1000"


def test_r1000_cohort_rows_both_sites(conn):
    for site in ("pokerbet", "sunbet"):
        fixtures = PB_DAY if site == "pokerbet" else load("sunbet_day.json")["tournaments"]
        ingest(conn, FixtureAdapter(site, copy.deepcopy(fixtures), {}, {}),
               run_id=f"coh-{site}", raw_dir=os.environ["MTT_RAW_DIR"])
    s = db.schema_name()
    rows = db.query(conn, f"SELECT t.site, COUNT(*) n FROM {s}.tournament_cohorts tc "
                          f"JOIN {s}.tournaments t ON t.id = tc.tournament_id "
                          "WHERE tc.cohort='R1000' GROUP BY t.site ORDER BY t.site")
    assert {r["site"]: r["n"] for r in rows} == {"pokerbet": 1, "sunbet": 1}
