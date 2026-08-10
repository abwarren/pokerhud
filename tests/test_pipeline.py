"""Integration tests: fixture adapter -> pipeline -> mtt_test DB.

Covers: ingestion, classification persistence, snapshots, results/players,
idempotency (double run), R1000 isolation, daily reconciliation.
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


@pytest.fixture()
def conn():
    c = db.connect()
    db.ensure_schema(c)
    reset_schema(c)
    yield c
    c.close()

def make_adapters():
    import copy
    return {
        "pokerbet": FixtureAdapter("pokerbet", copy.deepcopy(PB_DAY),
                                   copy.deepcopy(SNAPS), copy.deepcopy(RESULTS)),
        "sunbet": FixtureAdapter("sunbet", copy.deepcopy(SB_DAY),
                                 copy.deepcopy(SNAPS), copy.deepcopy(RESULTS)),
    }


class TestIngestion:
    def test_full_day_both_sites(self, conn):
        for site, adapter in make_adapters().items():
            counters = ingest(conn, adapter, run_id=f"e2e-{site}-1",
                              raw_dir=os.environ["MTT_RAW_DIR"])
            assert counters["status"] == "completed"
            assert counters["discovered"] == len(PB_DAY if site == "pokerbet" else SB_DAY)
            assert counters["failed"] == 0

        rows = db.query(conn, f"SELECT site, COUNT(*) n FROM {db.schema_name()}.tournaments GROUP BY site")
        by_site = {r["site"]: r["n"] for r in rows}
        assert by_site == {"pokerbet": 6, "sunbet": 4}

    def test_r1000_cohort_isolated(self, conn):
        ingest(conn, make_adapters()["pokerbet"], run_id="e2e-pb-r1000",
               raw_dir=os.environ["MTT_RAW_DIR"])
        rows = db.query(conn, f"SELECT name, buyin, buyin_band, cohort FROM {db.schema_name()}.tournaments WHERE site='pokerbet'")
        bands = {(r["name"], r["buyin_band"], r["cohort"]) for r in rows}
        assert ("1k Turbo Rebuy / Add-on", "R1000", "R1000") in bands
        assert ("Lunch Time 20k", "SMALL", "SMALL") in bands
        assert ("R2k High Roller", "HIGH", "HIGH") in bands
        assert ("Deep Freeze R50", "MICRO", "MICRO") in bands
        assert ("Sunday Slam R125k GTD", "MID", "MID") in bands

    def test_idempotent_double_run(self, conn):
        adapter = make_adapters()["pokerbet"]
        ingest(conn, adapter, run_id="e2e-run-1", raw_dir=os.environ["MTT_RAW_DIR"])
        ingest(conn, adapter, run_id="e2e-run-2", raw_dir=os.environ["MTT_RAW_DIR"])
        n = db.query(conn, f"SELECT COUNT(*) n FROM {db.schema_name()}.tournaments WHERE site='pokerbet'")[0]["n"]
        assert n == 6, f"expected 6 tournaments, got {n}"
        # snapshots: captured_at differs between runs (now()) -> more rows, no dupes
        snaps = db.query(conn, f"SELECT tournament_id, captured_at FROM {db.schema_name()}.tournament_snapshots")
        assert len(snaps) == len({(s["tournament_id"], s["captured_at"]) for s in snaps})

    def test_snapshots_written(self, conn):
        ingest(conn, make_adapters()["pokerbet"], run_id="e2e-snap",
               raw_dir=os.environ["MTT_RAW_DIR"])
        rows = db.query(conn, f"SELECT t.name, COUNT(s.id) n FROM {db.schema_name()}.tournaments t "
                              f"JOIN {db.schema_name()}.tournament_snapshots s ON s.tournament_id=t.id "
                              "WHERE t.site='pokerbet' GROUP BY t.name")
        by_name = {r["name"]: r["n"] for r in rows}
        # fixture adapter pops ONE snapshot per tick -> 1 per tournament per run
        assert by_name.get("1k Turbo Rebuy / Add-on") == 1
        assert by_name.get("Sunday Slam R125k GTD") == 1

    def test_results_players(self, conn):
        ingest(conn, make_adapters()["pokerbet"], run_id="e2e-res",
               raw_dir=os.environ["MTT_RAW_DIR"])
        players = db.query(conn, f"SELECT display_name, site FROM {db.schema_name()}.players")
        assert len(players) == 3
        pt = db.query(conn, f"SELECT p.display_name, pt.finish_position, pt.prize "
                            f"FROM {db.schema_name()}.player_tournaments pt "
                            f"JOIN {db.schema_name()}.players p ON p.id=pt.player_id")
        prizes = {(r["display_name"], r["finish_position"], r["prize"]) for r in pt}
        assert ("AceOfSpades", 1, 7800) in prizes

    def test_raw_events_preserved(self, conn):
        ingest(conn, make_adapters()["pokerbet"], run_id="e2e-raw",
               raw_dir=os.environ["MTT_RAW_DIR"])
        rows = db.query(conn, f"SELECT endpoint, COUNT(*) n FROM {db.schema_name()}.raw_events "
                              f"WHERE site='pokerbet' GROUP BY endpoint")
        by_ep = {r["endpoint"]: r["n"] for r in rows}
        assert by_ep["discover"] == 6
        assert by_ep["snapshot"] == 2
        assert by_ep["results"] == 1

    def test_quality_scores_persisted(self, conn):
        ingest(conn, make_adapters()["pokerbet"], run_id="e2e-q",
               raw_dir=os.environ["MTT_RAW_DIR"])
        rows = db.query(conn, f"SELECT name, data_quality_score FROM {db.schema_name()}.tournaments "
                              f"WHERE site='pokerbet'")
        by_name = {r["name"]: r["data_quality_score"] for r in rows}
        assert by_name["Sunday Slam R125k GTD"] == 100  # has prize_pool + entries
        assert by_name["1k Turbo Rebuy / Add-on"] < 100  # missing prize_pool
        assert by_name["Wacky Wednesday R125k GTD"] < 100  # missing prize_pool

    def test_bad_tournament_does_not_kill_run(self, conn):
        fixtures = [{"site": "pokerbet", "site_tournament_id": "good", "name": "Good"},
                    {"site": "pokerbet", "site_tournament_id": "bad",
                     "name": "Bad", "start_time": object()}]  # unnormalizable
        adapter = FixtureAdapter("pokerbet", fixtures)
        counters = ingest(conn, adapter, run_id="e2e-bad",
                          raw_dir=os.environ["MTT_RAW_DIR"])
        assert counters["failed"] == 1
        assert counters["captured"] == 1
        errs = db.query(conn, f"SELECT COUNT(*) n FROM {db.schema_name()}.parser_errors")
        assert errs[0]["n"] >= 1


class TestReconciliation:
    def test_daily_ledger(self, conn):
        for site, adapter in make_adapters().items():
            ingest(conn, adapter, run_id=f"e2e-daily-{site}",
                   raw_dir=os.environ["MTT_RAW_DIR"])
        report = ledger.reconcile(conn, date(2026, 8, 10))
        assert ("pokerbet", "R1000") in report
        assert ("pokerbet", "SMALL") in report
        assert ("sunbet", "R1000") in report
        assert ("sunbet", "MID") in report
        # prize pool total for pokerbet: 137000 (t1002) + 31200 (t1003)
        assert report[("pokerbet", "MID")]["prize_pool_total"] == 137000
        assert report[("pokerbet", "SMALL")]["prize_pool_total"] == 31200

    def test_ledger_persisted(self, conn):
        for site, adapter in make_adapters().items():
            ingest(conn, adapter, run_id=f"e2e-led-{site}",
                   raw_dir=os.environ["MTT_RAW_DIR"])
        ledger.reconcile(conn, date(2026, 8, 10))
        rows = db.query(conn, f"SELECT site, cohort, tournaments_expected FROM {db.schema_name()}.daily_statistics "
                              f"WHERE stat_date='2026-08-10'")
        keyed = {(r["site"], r["cohort"]): r["tournaments_expected"] for r in rows}
        assert keyed == {("pokerbet", "R1000"): 1, ("pokerbet", "SMALL"): 2,
                         ("pokerbet", "MID"): 1, ("pokerbet", "HIGH"): 1,
                         ("pokerbet", "MICRO"): 1, ("sunbet", "R1000"): 1,
                         ("sunbet", "SMALL"): 1, ("sunbet", "MID"): 1,
                         ("sunbet", "MICRO"): 1}

    def test_report_renders_cohorts(self, conn):
        for site, adapter in make_adapters().items():
            ingest(conn, adapter, run_id=f"e2e-rep-{site}",
                   raw_dir=os.environ["MTT_RAW_DIR"])
        report = ledger.reconcile(conn, date(2026, 8, 10))
        text = ledger.render_report(report, date(2026, 8, 10))
        assert "R1000" in text
        assert "POKERBET" in text
        assert "SUNBET" in text
        assert "expected=" in text
