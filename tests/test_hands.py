"""Hand/table schema tests: normalization + idempotent ingestion."""

import copy
import os

import pytest

from mtt import db, normalize
from mtt.adapters import FixtureAdapter
from mtt.pipeline import ingest

from helpers import load, reset_schema

PB_DAY = load("pokerbet_day.json")["tournaments"]
HANDS = load("hands.json")
SNAPS = load("snapshots.json")
RESULTS = load("results.json")


@pytest.fixture()
def conn():
    c = db.connect()
    db.ensure_schema(c)
    reset_schema(c)
    yield c
    c.close()


def make_adapter(site):
    return FixtureAdapter(site, copy.deepcopy(PB_DAY if site == "pokerbet"
                                               else load("sunbet_day.json")["tournaments"]),
                          copy.deepcopy(SNAPS), copy.deepcopy(RESULTS),
                          hands_map=copy.deepcopy(HANDS.get(site, {})))


def test_normalize_hand():
    raw = HANDS["pokerbet"]["t-1002"][0]
    h = normalize.normalize_hand({**raw, "site": "pokerbet"})
    assert h["site_hand_id"] == "pb-t1002-h000123"
    assert h["tournament_ref"] == "t-1002"
    assert h["table_ref"] == "tbl-7"
    assert h["board"] == "AhKhQh"
    assert h["final_pot"] == 15600
    assert len(h["players"]) == 2
    assert h["players"][0]["hole_cards"] == "AhKh"
    assert len(h["actions"]) == 5
    assert h["actions"][2]["action_type"] == "bet"
    assert h["actions"][2]["street"] == "flop"
    assert h["actions"][0]["action_order"] == 0
    assert h["actions"][4]["action_type"] == "win"


def test_normalize_hand_action_maps():
    a = normalize.normalize_hand_action(
        {"player": "X", "street": "Pre-flop", "action_type": "Raises", "amount": "400"}, 0)
    assert a["action_type"] == "raise"
    assert a["street"] == "preflop"
    assert a["amount"] == 400


def test_hands_ingested(conn):
    c = ingest(conn, make_adapter("pokerbet"), run_id="hands-1",
               raw_dir=os.environ["MTT_RAW_DIR"])
    assert c["status"] == "completed"
    assert c["hands"] == 2
    assert c["failed"] == 0
    s = db.schema_name()
    assert db.query(conn, f"SELECT COUNT(*) n FROM {s}.hands")[0]["n"] == 2
    assert db.query(conn, f"SELECT COUNT(*) n FROM {s}.tables")[0]["n"] == 1
    assert db.query(conn, f"SELECT COUNT(*) n FROM {s}.hand_players")[0]["n"] == 4
    assert db.query(conn, f"SELECT COUNT(*) n FROM {s}.hand_actions")[0]["n"] == 8
    # raw preserved for every hand
    raw = db.query(conn, f"SELECT COUNT(*) n FROM {s}.raw_events WHERE endpoint='hand'")
    assert raw[0]["n"] == 2
    # players reused (no new identities for existing names)
    assert db.query(conn, f"SELECT COUNT(*) n FROM {s}.players")[0]["n"] == 3


def test_hands_idempotent_double_run(conn):
    ingest(conn, make_adapter("pokerbet"), run_id="hands-2a",
           raw_dir=os.environ["MTT_RAW_DIR"])
    c2 = ingest(conn, make_adapter("pokerbet"), run_id="hands-2b",
                raw_dir=os.environ["MTT_RAW_DIR"])
    assert c2["duplicates"] > 0
    s = db.schema_name()
    n = db.query(conn, f"SELECT COUNT(*) n FROM {s}.hands")[0]["n"]
    assert n == 2, "second run must not duplicate hands"
    assert db.query(conn, f"SELECT COUNT(*) n FROM {s}.hand_actions")[0]["n"] == 8


def test_sunbet_hands_ingested(conn):
    c = ingest(conn, make_adapter("sunbet"), run_id="hands-sb",
               raw_dir=os.environ["MTT_RAW_DIR"])
    assert c["hands"] == 1
    s = db.schema_name()
    assert db.query(conn, f"SELECT COUNT(*) n FROM {s}.hands")[0]["n"] == 1
    assert db.query(conn, f"SELECT COUNT(*) n FROM {s}.tables")[0]["n"] == 1


def test_bad_hand_does_not_kill_run(conn):
    good = copy.deepcopy(HANDS["pokerbet"]["t-1002"][0])
    bad = copy.deepcopy(good)
    bad["site_hand_id"] = "pb-bad-hand"
    bad["players"] = [{"display_name": "X"}, "garbage-not-a-dict"]  # unnormalizable
    adapter = FixtureAdapter("pokerbet", copy.deepcopy(PB_DAY),
                             snapshots={}, results_map={},
                             hands_map={"t-1002": [good, bad]})
    c = ingest(conn, adapter, run_id="hands-bad", raw_dir=os.environ["MTT_RAW_DIR"])
    assert c["hands"] == 1
    assert c["failed"] == 1
    s = db.schema_name()
    errs = db.query(conn, f"SELECT error_type, COUNT(*) n FROM {s}.parser_errors "
                          f"GROUP BY error_type")
    assert {r["error_type"] for r in errs} == {"HAND_ERROR"}
