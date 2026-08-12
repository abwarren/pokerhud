"""Slice 7 — auto-actions engine + trigger tests (no DB, Flask test client)."""

import os
import tempfile

# Isolate persistence from the real state file (PUT auto-rules persists).
os.environ["N4P_STATE_FILE"] = os.path.join(tempfile.mkdtemp(prefix="hermes-verify-"), "state.json")

import pytest

from webapp import auto_actions as aa

API_KEY = "test123"

SNAP = {
    "table_id": "T-AUTO",
    "dealer_seat": 1,
    "deal_id": "h1",
    "site": "pokerbet",
    "seats": [{"name": "hero", "seat_index": 0, "is_hero": True,
               "stack_zar": 100, "hole_cards": ["Ah", "Kh"]}],
    "street": "preflop",
    "pot_zar": 10,
}

# module-level stores are shared across tests — unique table per test
T_CC, T_OFF, T_DUP = "T-AUTO-CC", "T-AUTO-OFF", "T-AUTO-DUP"


# ── pure engine ────────────────────────────────────────────────────────────────

def test_cf_checks_when_free_folds_when_bet():
    assert aa.decide("cf", ["check", "call", "raise"]) == {"type": "check", "amount": None}
    assert aa.decide("cf", ["fold", "call"]) == {"type": "fold", "amount": None}


def test_cf_hands_off_when_only_call_raise():
    assert aa.decide("cf", ["call", "raise"]) is None


def test_cc_checks_when_free_calls_when_bet():
    assert aa.decide("cc", ["check", "call"]) == {"type": "check", "amount": None}
    assert aa.decide("cc", ["fold", "call"]) == {"type": "call", "amount": None}


def test_cc_hands_off_when_cannot_check_or_call():
    assert aa.decide("cc", ["fold", "raise"]) is None


def test_kh_always_raises_bets_then_calls_checks():
    assert aa.decide("kh", ["fold", "call", "raise"]) == {"type": "raise", "amount": None}
    assert aa.decide("kh", ["fold", "check", "bet"]) == {"type": "bet", "amount": None}
    assert aa.decide("kh", ["fold", "call"]) == {"type": "call", "amount": None}
    assert aa.decide("kh", ["check"]) == {"type": "check", "amount": None}


def test_off_and_empty_actions_return_none():
    assert aa.decide("off", ["check", "call"]) is None
    assert aa.decide("cf", []) is None
    assert aa.decide("cf", None) is None


def test_validate_rule_rejects_junk():
    with pytest.raises(aa.AutoActionError):
        aa.validate_rule("all-in-always")


def test_normalize_actions_tolerates_junk():
    assert aa.normalize_actions(["CHECK", "check", "bogus", "RaIsE"]) == ["check", "raise"]


# ── integration: trigger via API ───────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _api_key():
    from webapp import remote_bp as rb
    rb.TRACKER_API_KEY = API_KEY
    yield


def _client():
    from webapp import create_app
    return create_app().test_client()


def test_cc_rule_auto_queues_call_on_hero_turn():
    from webapp import remote_bp as rb
    rb._auto_rules.clear()
    c = _client()
    assert c.put(f"/api/auto-rules/pokerbet/{T_CC}", json={"rule": "cc"}).status_code == 200
    r = c.post("/api/snapshot", json={**SNAP, "table_id": T_CC, "available_actions": ["fold", "call"]},
               headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    # hero seat 1 token — command should be auto-queued as call
    tok = rb.generate_seat_token("pokerbet", T_CC, 1)
    pend = c.get(f"/api/commands/pending?token={tok}").get_json()
    assert pend["command"]["type"] == "call"
    assert pend["command"].get("source") == "auto"


def test_rule_off_does_not_auto_queue():
    from webapp import remote_bp as rb
    rb._auto_rules.clear()
    c = _client()
    c.put(f"/api/auto-rules/pokerbet/{T_OFF}", json={"rule": "off"})
    c.post("/api/snapshot", json={**SNAP, "table_id": T_OFF, "available_actions": ["fold", "call"]},
           headers={"X-API-Key": API_KEY})
    tok = rb.generate_seat_token("pokerbet", T_OFF, 1)
    pend = c.get(f"/api/commands/pending?token={tok}").get_json()
    assert pend["command"] is None


def test_no_duplicate_auto_commands():
    from webapp import remote_bp as rb
    rb._auto_rules.clear()
    c = _client()
    c.put(f"/api/auto-rules/pokerbet/{T_DUP}", json={"rule": "cc"})
    for _ in range(3):  # hero stays on turn across snapshots
        c.post("/api/snapshot", json={**SNAP, "table_id": T_DUP, "available_actions": ["fold", "call"]},
               headers={"X-API-Key": API_KEY})
    tok = rb.generate_seat_token("pokerbet", T_DUP, 1)
    pend = c.get(f"/api/commands/pending?token={tok}").get_json()
    assert pend["command"] is not None  # one pending, not three
    assert pend["command"]["type"] == "call"
