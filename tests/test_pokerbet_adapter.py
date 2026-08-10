"""PokerBet adapter unit tests — BetConstruct CMS/WS parsing (fixture-driven)."""

import pytest

from mtt import classifier
from mtt.adapters.pokerbet import PokerBetAdapter, parse_zar_amount, strip_html

from helpers import load

CMS = load("pokerbet_cms.json")
WS = load("pokerbet_ws.json")["tournaments"]


@pytest.fixture()
def adapter():
    a = PokerBetAdapter(use_ws=False)
    return a


def test_strip_html():
    assert strip_html("<p>Buy-in of <strong>R700</strong>+R70</p>") == " Buy-in of  R700 +R70 "


def test_parse_zar_amount():
    assert parse_zar_amount("Guaranteed R200,000 pool") == 200000
    assert parse_zar_amount("R 1 250 entry") == 1250
    assert parse_zar_amount("no money here") is None


def test_cms_buyin_fee_spaced_and_compact(adapter):
    t = adapter._cms_to_tournament(CMS["data"][0])   # R700+R70
    assert t["buyin"] == 700 and t["fee"] == 70 and t["total_entry_cost"] == 770
    assert t["guarantee"] == 200000
    assert t["game_type"] is None                    # promo text doesn't state it
    assert t["status"] == "scheduled"
    assert t["start_time"] is None                    # no date in CMS page
    assert t["start_time_raw"] == "06:00 pm"          # raw hint preserved


def test_cms_buyin_fee_spaced(adapter):
    t = adapter._cms_to_tournament(CMS["data"][1])   # R250 + R25
    assert t["buyin"] == 250 and t["fee"] == 25
    assert t["guarantee"] == 125000


def test_cms_bare_buyin_and_satellite(adapter):
    t = adapter._cms_to_tournament(CMS["data"][2])   # EPT package R1,999
    assert t["buyin"] == 1999
    assert t["format"] == "SATELLITE"
    classifier.classify_tournament(t)
    assert t["cohort"] == "HIGH"


def test_cms_missing_buyin_keeps_none(adapter):
    t = adapter._cms_to_tournament(CMS["data"][3])   # Monday Madness
    assert t["buyin"] is None
    assert t["guarantee"] == 125000


def test_cms_non_poker_filtered(adapter):
    assert adapter._cms_to_tournament(CMS["data"][4]) is None   # casino promo
    assert adapter._cms_to_tournament(CMS["data"][6]) is None   # rake back Ts&Cs
    assert adapter._cms_to_tournament(CMS["data"][7]) is None   # refer a friend


def test_cms_live_payload_real_capture(adapter):
    """Real 2026-08-11 CMS payload: only the Sunday Slam survives filtering."""
    live = load("pokerbet_cms_live.json")
    tours = [t for t in (adapter._cms_to_tournament(item) for item in live["data"])
             if t]
    assert len(tours) == 1, [t["name"] for t in tours]
    t = tours[0]
    assert t["site_tournament_id"] == "cms-109866"
    assert t["name"] == "Sunday Slam R200k Guaranteed"
    assert t["buyin"] == 700 and t["fee"] == 70 and t["total_entry_cost"] == 770
    assert t["guarantee"] == 250000
    assert t["start_time_raw"] == "06:00 pm"   # adapter canonicalizes '6:00pm'
    classifier.classify_tournament(t)
    assert t["cohort"] == "MID"            # buyin 700, GTD 250k — not the R1k tier


def test_cms_r1000_buyin(adapter):
    t = adapter._cms_to_tournament(CMS["data"][5])   # 1k Turbo
    assert t["buyin"] == 1000 and t["guarantee"] == 1000
    classifier.classify_tournament(t)
    # R1000 = the R1,000 GUARANTEE tier
    assert t["cohort"] == "R1000"
    assert t["buyin_band"] == "HIGH"


def test_ws_to_tournament(adapter):
    from mtt import normalize
    t = normalize.normalize_tournament(adapter._ws_to_tournament("501234", WS[0]))
    assert t["site_tournament_id"] == "501234"
    assert t["buyin"] == 500 and t["fee"] == 50
    assert t["entries"] == 412
    assert t["prize_pool"] == 137000
    assert t["guarantee"] == 125000
    assert t["status"] == "running"
    assert t["start_time"].endswith("+00:00") or t["start_time"].endswith("Z")


def test_ws_r1000_and_game_type(adapter):
    from mtt import classifier, normalize
    t = normalize.normalize_tournament(adapter._ws_to_tournament("501235", WS[1]))
    classifier.classify_tournament(t)
    assert t["cohort"] == "R1000"
    o = normalize.normalize_tournament(adapter._ws_to_tournament("501236", WS[2]))
    assert o["game_type"] == "PLO"     # 'Omaha Hi-Lo 5k'


def test_discover_cms_only_without_token(adapter):
    tours = adapter.discover()
    assert tours  # CMS-only mode still discovers promotions
    assert adapter.ws_stale is True
    for t in tours:
        assert t["source"] == "cms"


def test_discover_dedupes_ws_over_cms(monkeypatch, adapter):
    """WS wins for the same tournament ref."""
    adapter.token, adapter.client_id = "x", "y"          # tokens present
    adapter._ws_live = lambda: None                       # no network
    adapter._ws_tournaments = {str(w["id"]): w for w in WS}
    tours = {t["site_tournament_id"]: t for t in adapter.discover()}
    assert tours["501234"]["source"] == "ws"
    assert tours["501235"]["source"] == "ws"
    assert not adapter.ws_stale


def test_snapshot_fields(adapter):
    adapter._ws_tournaments = {"501234": WS[0]}
    snap = adapter.snapshot("501234")
    assert snap["entries"] == 412
    assert snap["players_remaining"] == 288
    assert snap["tables_active"] == 24
    assert snap["status"] == "running"
    assert snap["late_registration"] is True
    assert adapter.snapshot("nope") is None


def test_results_not_exposed(adapter):
    assert adapter.results("501234") is None


def test_hand_data_empty_without_endpoint(adapter):
    assert adapter.hand_data("501234") == []
