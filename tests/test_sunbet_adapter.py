"""SunBet adapter unit tests — EvenBet lobby parsing (fixture-driven)."""

import json

from mtt import classifier
from mtt.adapters.sunbet import (SunBetAdapter, merge_row_detail,
                                 parse_detail_panel, parse_file_payload,
                                 parse_lobby_rows)

from helpers import load

LOBBY = load("sunbet_lobby.json")


def test_parse_lobby_rows_high_buyin_band():
    # R1,000 buy-in = HIGH band (R1000 cohort = R1,000 GUARANTEE, not buy-in)
    rows = parse_lobby_rows(LOBBY["rows"])
    by_name = {r["name"]: r for r in rows}
    t = by_name["Tuesday Main Re-Entry"]
    assert t["buyin"] == 1000
    assert t["fee"] == 100
    assert t["total_entry_cost"] == 1100
    assert t["status"] == "registration"
    assert t["entries"] == 0
    assert t["site"] == "sunbet"
    classifier.classify_tournament(t)
    assert t["buyin_band"] == "HIGH"
    assert t["cohort"] == "HIGH"          # no R1000 guarantee in the row data


def test_parse_lobby_rows_bounty_and_bands():
    rows = {r["name"]: r for r in parse_lobby_rows(LOBBY["rows"])}
    ko = rows["Wednesday Main KO"]
    assert ko["buyin"] == 400 and ko["fee"] == 80 and ko["total_entry_cost"] == 880
    classifier.classify_tournament(ko)
    assert ko["cohort"] == "SMALL"        # 400 falls in SMALL, not R1000
    freeroll = rows["Morning Glory Freeroll"]
    assert freeroll["buyin"] == 0
    classifier.classify_tournament(freeroll)
    assert freeroll["cohort"] == "MICRO"
    spin = rows["R1 Spin Up"]
    assert spin["buyin"] == 1
    classifier.classify_tournament(spin)
    assert spin["cohort"] == "MICRO"


def test_parse_lobby_rows_status_and_completed():
    rows = {r["name"]: r for r in parse_lobby_rows(LOBBY["rows"])}
    assert rows["Mini Stack"]["status"] == "registration"
    done = rows["Monday Main Re-Buy"]
    assert done["status"] == "completed"      # from row status
    assert done["entries"] == 43
    assert done["prize_pool"] == 25000


def test_parse_lobby_rows_start_time():
    rows = {r["name"]: r for r in parse_lobby_rows(LOBBY["rows"])}
    st = rows["Tuesday Main Re-Entry"]["start_time"]
    assert st is not None
    assert st.endswith("+00:00") or st.endswith("Z")   # UTC ISO


def test_parse_detail_panel_overrides():
    d = parse_detail_panel(LOBBY["details"]["Tuesday Main Re-Entry"])
    assert d["site_tournament_id"] == "8599"          # '#' stripped
    assert d["name"] == "Tuesday Main Re-Entry"
    assert d["game_type"] == "NLHE"                   # 'Hold'em NL' normalized
    assert d["status"] == "registration"
    assert d["prize_pool"] == 65000
    assert d["guarantee"] == 65000
    assert d["buyin"] == 1000 and d["fee"] == 100


def test_merge_row_detail_id_wins():
    row = parse_lobby_rows(LOBBY["rows"])[3]          # Tuesday Main Re-Entry
    detail = parse_detail_panel(LOBBY["details"]["Tuesday Main Re-Entry"])
    merged = merge_row_detail(row, detail)
    assert merged["site_tournament_id"] == "8599"
    assert merged["name"] == "Tuesday Main Re-Entry"


def test_parse_file_payload_full_lobby():
    tours = parse_file_payload(LOBBY)
    by_id = {t.get("site_tournament_id"): t for t in tours}
    assert len(tours) == 8
    tue = by_id["8599"]
    assert tue["buyin"] == 1000 and tue["guarantee"] == 65000
    classifier.classify_tournament(tue)
    assert tue["cohort"] == "HIGH"        # R65k guarantee, not the R1k tier
    # Mini Stack carries a R1,000 GUARANTEE -> dedicated R1000 cohort
    mini = by_id["8602"]
    assert mini["guarantee"] == 1000
    classifier.classify_tournament(mini)
    assert mini["cohort"] == "R1000"
    # rows without detail get a name-based id via the normalizer later
    assert any(t["name"] == "Monday Main Re-Buy" for t in tours)


def test_parse_file_payload_bare_list():
    tours = parse_file_payload(LOBBY["rows"])
    assert len(tours) == 8
    assert tours[0]["name"] == "Morning Glory Freeroll"


def test_adapter_file_mode_consumes_input(tmp_path):
    (tmp_path / "lobby.json").write_text(json.dumps(LOBBY))
    adapter = SunBetAdapter(input_dir=str(tmp_path))
    tours = adapter.discover()
    assert len(tours) == 8
    # file consumed -> moved to processed/, second discover is empty
    assert (tmp_path / "processed" / "lobby.json").exists()
    assert adapter.discover() == []


def test_adapter_no_source_sets_error():
    adapter = SunBetAdapter()
    assert adapter.discover() == []
    assert adapter.last_error and "no collection source" in adapter.last_error


def test_adapter_results_and_hands_unavailable():
    adapter = SunBetAdapter()
    assert adapter.results("8599") is None
    assert adapter.hand_data("8599") == []
