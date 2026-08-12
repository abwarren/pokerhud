"""Slice 4 — tenant isolation regression tests (no DB, Flask test client).

Two sites posting snapshots for the SAME table_id must not collide: state,
seat tokens, and command queues are site-scoped.

Note: remote_bp caches TRACKER_API_KEY at import; in the full suite another
test module imports webapp before this file, so env timing can't be trusted —
we patch the module global via a fixture instead.
"""

import pytest

from webapp import create_app  # noqa: E402
from webapp import remote_bp as rb  # noqa: E402

API_KEY = "test123"


@pytest.fixture(scope="module", autouse=True)
def _api_key():
    rb.TRACKER_API_KEY = API_KEY
    yield

SNAP = {
    "table_id": "T1",
    "dealer_seat": 1,
    "deal_id": "h1",
    "seats": [{"name": "hero", "seat_index": 0, "is_hero": True,
               "stack_zar": 100, "hole_cards": ["Ah", "Kh"]}],
    "street": "preflop",
    "pot_zar": 10,
}


def _post_snapshot(client, site):
    return client.post("/api/snapshot", json={**SNAP, "site": site},
                       headers={"X-API-Key": API_KEY})


def test_two_sites_same_table_no_collision():
    app = create_app()
    c = app.test_client()

    r1 = _post_snapshot(c, "pokerbet")
    assert r1.status_code == 200 and r1.get_json()["ok"] is True
    r2 = _post_snapshot(c, "sunbet")
    assert r2.status_code == 200 and r2.get_json()["ok"] is True

    tables = c.get("/api/tables").get_json()
    entries = (tables or {}).get("tables") if isinstance(tables, dict) else tables
    assert entries, f"unexpected /api/tables shape: {tables!r}"
    sites = {t.get("site") for t in entries if t.get("table_id") == "T1"}
    assert sites == {"pokerbet", "sunbet"}, f"site bleed: {sites}"


def test_multi_hero_cards_isolated():
    """Two heroes in one snapshot must each keep their OWN hole cards
    (regression: last hero's seat got the FIRST hero's cards via the
    post-loop single-hero cache — broke the equity panel with dup cards)."""
    app = create_app()
    c = app.test_client()
    SNAP2 = {
        "table_id": "T-MH", "dealer_seat": 1, "deal_id": "h1", "site": "pokerbet",
        "seats": [
            {"name": "hero1", "seat_index": 0, "is_hero": True, "stack_zar": 100,
             "hole_cards": ["Ah", "Kh", "Qh", "Jh"]},
            {"name": "hero2", "seat_index": 1, "is_hero": True, "stack_zar": 100,
             "hole_cards": ["Ad", "Kd", "Qd", "Jd"]}],
        "street": "flop", "pot_zar": 50,
        "board": {"flop": ["2c", "7s", "9d"], "turn": None, "river": None},
    }
    r = c.post("/api/snapshot", json=SNAP2, headers={"X-API-Key": API_KEY})
    assert r.status_code == 200

    tables = c.get("/api/tables").get_json()
    entries = (tables or {}).get("tables") if isinstance(tables, dict) else tables
    t = next(x for x in entries if x.get("table_id") == "T-MH")
    by_name = {s.get("name"): s.get("hole_cards") for s in t.get("seats", []) if s.get("name")}
    assert by_name["hero1"] == ["Ah", "Kh", "Qh", "Jh"]
    assert by_name["hero2"] == ["Ad", "Kd", "Qd", "Jd"]


def test_seat_tokens_are_site_scoped():
    from webapp import remote_bp as rb

    t_pb = rb.generate_seat_token("pokerbet", "T1", 1)
    t_sb = rb.generate_seat_token("sunbet", "T1", 1)
    assert t_pb != t_sb  # identical table/seat on different sites -> distinct tokens
    assert rb.generate_seat_token("pokerbet", "T1", 1) == t_pb  # deterministic


def test_command_queues_do_not_cross_sites():
    app = create_app()
    c = app.test_client()

    _post_snapshot(c, "pokerbet")
    _post_snapshot(c, "sunbet")

    tok_pb = rb.generate_seat_token("pokerbet", "T1", 1)
    tok_sb = rb.generate_seat_token("sunbet", "T1", 1)

    # queue a fold on pokerbet seat 1 only (site-scoped contract)
    r = c.post("/api/commands/queue", json={
        "site": "pokerbet", "table_id": "T1", "command_type": "fold", "seat_no": 1,
    })
    assert r.status_code == 200, r.get_json()

    pend_pb = c.get(f"/api/commands/pending?token={tok_pb}").get_json()
    pend_sb = c.get(f"/api/commands/pending?token={tok_sb}").get_json()
    assert pend_pb.get("command", {}).get("type") == "fold"
    assert pend_sb.get("command") in (None, {}), "command bled across sites"
