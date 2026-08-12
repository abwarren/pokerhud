"""Slice 6 — SSE push regression tests (no DB, Flask test client).

Covers: snapshot/queue mutations broadcast to subscribers; the /api/events
endpoint streams text/event-stream and pushes the initial state.
"""

import json

import pytest

from webapp import create_app  # noqa: E402
from webapp import remote_bp as rb  # noqa: E402

API_KEY = "test123"

SNAP = {
    "table_id": "T9",
    "dealer_seat": 1,
    "deal_id": "h1",
    "seats": [{"name": "hero", "seat_index": 0, "is_hero": True,
               "stack_zar": 100, "hole_cards": ["Ah", "Kh"]}],
    "street": "preflop",
    "pot_zar": 10,
    "site": "pokerbet",
}


@pytest.fixture(scope="module", autouse=True)
def _api_key():
    rb.TRACKER_API_KEY = API_KEY
    yield


def test_snapshot_broadcasts_to_subscriber():
    app = create_app()
    c = app.test_client()
    r = c.post("/api/snapshot", json=SNAP, headers={"X-API-Key": API_KEY})
    assert r.status_code == 200

    from queue import Queue
    q = Queue(maxsize=1)
    with rb._sse_lock:
        rb._sse_subs.add(q)
    try:
        # mutate state -> broadcast
        r2 = c.post("/api/snapshot", json={**SNAP, "street": "flop"},
                    headers={"X-API-Key": API_KEY})
        assert r2.status_code == 200
        payload = json.loads(q.get(timeout=2))
        assert payload["type"] == "table"
        assert payload["table"]["street"] == "flop"
        assert payload["table"]["table_id"] == "T9"
    finally:
        with rb._sse_lock:
            rb._sse_subs.discard(q)


def test_events_endpoint_streams_initial_state():
    app = create_app()
    c = app.test_client()
    c.post("/api/snapshot", json={**SNAP, "table_id": "T9b", "deal_id": "h2"},
           headers={"X-API-Key": API_KEY})

    r = c.get("/api/events", buffered=False)
    try:
        assert r.status_code == 200
        assert r.mimetype == "text/event-stream"
        assert "Cache-Control" in r.headers
        chunk = next(iter(r.response))  # first yield = initial state (immediate)
        assert b'"type": "table"' in (chunk.encode() if isinstance(chunk, str) else chunk)
    finally:
        r.close()
