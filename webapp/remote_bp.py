"""
PLO Remote Table Control - Flask Backend v3
Stability fixes over v2:
  P1 - _tables persisted to disk every 10s, reloaded on startup
  P2 - Stale seats evicted after SEAT_TTL seconds (background thread)
  P2 - Commands expire after CMD_TTL seconds (same thread)
  P2 - Disk writes moved outside _store_lock scope
  P3 - All print() replaced with current_app.logger (goes to journald)
  P3 - Rate limiting via flask-limiter (1 snapshot/sec per token)
  P3 - systemd restart protection in service file (see bottom comment)
Site tenancy (slice 4a): one app, tenants = poker sites.
  P4 - All remote-control state is keyed by (site, table_id): _tables,
       _seat_bots, _hero_cards; seat tokens are HMAC(site:table_id:seat_no);
       _bot_seats/_bot_actions/_bot_buttons are site-aware. Sites:
       'pokerbet' | 'sunbet' (goldrush is betconstruct → 'pokerbet').
       Backward compatible: payloads without 'site' resolve to 'pokerbet'.
"""

import os
import sys
import time
import hmac
import hashlib
import threading
import uuid
import logging
from datetime import datetime
from pathlib import Path
import json
from queue import Empty, Queue
from flask import (Blueprint, current_app, request, jsonify,
                    send_from_directory, send_file, make_response)
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ── App setup ──────────────────────────────────────────────────────────────────

remote_bp = Blueprint("remote", __name__)

# PNA header handled by create_app()'s after_request (see webapp/__init__.py) —
# not duplicated here.


# Send Flask logs to stdout so systemd/journald captures them
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout,
)


# Rate limiter — 1 snapshot per second per IP (init_app called by create_app factory)
# Install: pip install flask-limiter --break-system-packages
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],          # no global limit; apply per route
    storage_uri="memory://",
)



# Helper decorator for admin-only routes



# ── Environment ────────────────────────────────────────────────────────────────

from .config import (N4P_SEAT_SECRET, TRACKER_API_KEY, SEAT_TTL, CMD_TTL,
                     PERSIST_INT, STATE_FILE, STATIC_DIR)
from . import auto_actions

# Logger level is set inside start_background() (needs app context) — not here.

# ── In-memory stores ───────────────────────────────────────────────────────────

_tables        = {}   # key: (site, table_id) → canonical table state
_command_queue = {}   # key: seat_token → command dict or None
_cashout_state = {}   # key: seat_token → {requested, available}
_bot_seats     = {}   # key: bot_id → {"site": str, "table_id": str, "seat_no": int, "last_seen": float}
_seat_bots     = {}   # key: (site, table_id, seat_no) → bot_id
_hero_cards    = {}   # key: (site, table_id, seat_no) → [card, card, ...] — persists across snapshots
_bot_actions   = {}   # key: (site, bot_id) → ["fold", "check", ...] — latest available actions from DOM
_bot_buttons   = {}   # key: (site, bot_id) → {actions:[...], presets:[...], slider:{...}} — full detection
_store_lock    = threading.Lock()

# Last-known-good table view cache (prevents UI flicker on partial/empty state)
_last_good_view = None   # {"view": dict, "ts": float}
_STALE_MAX_AGE  = 5.0    # seconds: max age before stale cache expires

# ── Auto-action rules (slice 7) ────────────────────────────────────────────────
# key: (site, table_id) → rule ('off' | 'cf' | 'cc' | 'kh'). Persisted in the
# state file under the reserved "_auto_rules" key (skipped by the table loader).
_auto_rules = {}

# ── SSE push (slice 6) ─────────────────────────────────────────────────────────
# Subscribers are bounded queues (maxsize=1, drop-old) so a slow client never
# blocks the snapshot path. Heartbeat keeps proxies from closing idle streams.
_sse_subs   = set()
_sse_lock   = threading.Lock()
_SSE_HEARTBEAT = 15.0

def _sse_latest_view():
    """Build the latest known-good table view for push (None if no state)."""
    with _store_lock:
        if _last_good_view and (time.time() - _last_good_view['ts']) < _STALE_MAX_AGE:
            return _last_good_view['view']
        if _tables:
            latest = max(_tables.values(), key=lambda t: t.get("last_ts", 0))
            return _table_view(latest)
        return None

def _notify_sse():
    """Broadcast the latest table view to all SSE subscribers (drop-old)."""
    view = _sse_latest_view()
    if view is None:
        return
    payload = json.dumps({"type": "table", "table": view}, default=str)
    with _sse_lock:
        for q in list(_sse_subs):
            try:
                q.get_nowait()
            except Empty:
                pass
            q.put_nowait(payload)

@remote_bp.route('/api/events')
def sse_events():
    """Server-sent events: pushes 'table' events on state change + heartbeat."""
    def gen():
        q = Queue(maxsize=1)
        with _sse_lock:
            _sse_subs.add(q)
        try:
            view = _sse_latest_view()
            if view is not None:
                yield f"data: {json.dumps({'type': 'table', 'table': view}, default=str)}\n\n"
            while True:
                try:
                    payload = q.get(timeout=_SSE_HEARTBEAT)
                    yield f"data: {payload}\n\n"
                except Empty:
                    yield ": keepalive\n\n"
        finally:
            with _sse_lock:
                _sse_subs.discard(q)

    resp = make_response(gen())
    resp.mimetype = "text/event-stream"
    resp.headers["Cache-Control"] = "no-cache, no-store"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp

# ── Hand history (multi-hand ASCII log, FIFO last 20) ──────────────────────────
_hand_history  = []   # list of ASCII hand strings, newest last, max 20
_hand_lock     = threading.Lock()
HAND_HISTORY_MAX = 20

# ── Static file serving ────────────────────────────────────────────────────────

@remote_bp.route("/remote")
@remote_bp.route("/remote/")
def remote_w4p():
    """W4P Remote Table Control — per-seat button mirror"""
    resp = make_response(send_from_directory(str(STATIC_DIR), "remote-w4p.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@remote_bp.route("/remotebutton")
def remotebutton():
    """Per-seat button control UI (PokerBet style)"""
    resp = make_response(send_from_directory(str(STATIC_DIR), "remotebutton.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@remote_bp.route("/shell")
def shell():
    """Frontend shell for monitoring all services"""
    return send_from_directory(str(STATIC_DIR), "shell-live.html")
@remote_bp.route("/n4p.js")
def n4p_script():
    resp = send_from_directory(str(STATIC_DIR), "n4p.js")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@remote_bp.route("/w4p.js")
def w4p_script():
    resp = send_from_directory(str(STATIC_DIR), "w4p.js")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

# ── Helpers ────────────────────────────────────────────────────────────────────

def _archive_hand(table):
    """Archive the current hand as ASCII text and append to _hand_history.
    Called when hand_key changes (new deal detected).
    Format: hole cards line, flop line, turn line, river line, separator.
    No labels, no words, only cards. One line per street."""
    seats = table.get("seats", {})
    board = table.get("board", {})
    flop  = board.get("flop") or []
    turn  = board.get("turn")
    river = board.get("river")

    # Find hero seat hole cards (or any seat with hole cards)
    hole_cards = []
    for seat in seats.values():
        hc = seat.get("hole_cards") or []
        if hc:
            hole_cards = hc
            break

    # Fallback: check _hero_cards cache (seats may have been overwritten by another bot)
    if not hole_cards:
        table_id = table.get("table_id")
        site = table.get("site")
        if table_id:
            for (sid, tid, sno), cards in _hero_cards.items():
                if sid == site and tid == table_id and cards:
                    hole_cards = list(cards)
                    break

    if not hole_cards:
        return  # Nothing to archive

    lines = []
    lines.append("".join(hole_cards))
    if flop:
        lines.append("".join(flop))
    if turn:
        lines.append(turn)
    if river:
        lines.append(river)
    lines.append("------------------------")

    hand_text = "\n".join(lines)

    with _hand_lock:
        _hand_history.append(hand_text)
        if len(_hand_history) > HAND_HISTORY_MAX:
            _hand_history[:] = _hand_history[-HAND_HISTORY_MAX:]


def normalize_name(name):
    if not name:
        return None
    return str(name).strip().lower()


def make_hand_key(payload):
    return f"{payload.get('table_id')}:{payload.get('dealer_seat')}:{payload.get('deal_id')}"


def generate_seat_token(site, table_id, seat_no):
    """Stateless HMAC seat token — site-scoped so identical table/seat
    numbers on different sites never collide."""
    msg = f"{site}:{table_id}:{seat_no}".encode('utf-8')
    return hmac.new(N4P_SEAT_SECRET.encode('utf-8'), msg, hashlib.sha256).hexdigest()


def get_or_create_table(site, table_id):
    key = (site, table_id)
    if key not in _tables:
        _tables[key] = {
            "site":          site,
            "table_id":      table_id,
            "hand_key":      None,
            "state_version": 0,
            "last_ts":       0,
            "seats":         {},
            "seat_map":      {},
            "next_seat_no":  1,
            "variant":       "plo",
            "street":        None,
            "pot_zar":       0,
            "raw_batch":     None,  # V2: Store raw collector batch (cleared on hand reset)
            "board":         {"flop": [], "turn": None, "river": None},
            "dealer_seat":   None,
        }
    return _tables[key]


def update_bot_seat_mapping(bot_id, site, table_id, seat_no):
    """
    Update bidirectional bot-seat mapping (site-scoped).
    Called with seat_no (not seat_index) so cache keys match _build_seats_list.
    """
    if not bot_id or bot_id == 'unknown-bot':
        return  # Don't track unknown bots

    ts = time.time()

    # Update bot → seat mapping
    _bot_seats[bot_id] = {
        "site": site,
        "table_id": table_id,
        "seat_no": seat_no,
        "last_seen": ts
    }

    # Update seat → bot mapping (keyed by seat_no to match _build_seats_list)
    seat_key = (site, table_id, seat_no)
    _seat_bots[seat_key] = bot_id

    current_app.logger.info(f'[BOT_SYNC] {bot_id} → {site}/{table_id}:seat_no={seat_no}')


def clear_bot_seat(bot_id):
    """Remove bot from seat mapping (called when bot unseats)"""
    if bot_id not in _bot_seats:
        return

    info = _bot_seats[bot_id]
    seat_key = (info.get("site"), info["table_id"], info.get("seat_no", info.get("seat_index")))

    # Clear bidirectional mapping
    if seat_key in _seat_bots and _seat_bots[seat_key] == bot_id:
        del _seat_bots[seat_key]

    del _bot_seats[bot_id]
    current_app.logger.info(f'[BOT_SYNC] {bot_id} unseated')


def _build_seats_list(table):
    out = []
    site = table.get("site")
    # Always build exactly 9 seats for 9-max tables
    max_seats = 9
    for seat_no in range(1, max_seats + 1):
        seat = table["seats"].get(seat_no)
        token = generate_seat_token(site, table["table_id"], seat_no)
        cmd = _command_queue.get(token)
        pending_cmd = cmd["type"] if cmd and cmd.get("status") == "pending" else None

        # Look up bot identity for this seat
        seat_key = (site, table["table_id"], seat_no)
        bot_id = _seat_bots.get(seat_key)

        if seat:
            seat_data = dict(seat)
            is_self = seat_data.get("is_hero", False) or bot_id is not None
            if is_self:
                # Self-player: use cached hero cards if available
                cached = _hero_cards.get((site, table["table_id"], seat_no), [])
                seat_data["hole_cards"] = cached if cached else seat_data.get("hole_cards", [])
                seat_data["is_self_player"] = True
                # Attach available actions from DOM scrape
                seat_data["available_actions"] = _bot_actions.get((site, bot_id), []) if bot_id else []
                seat_data["buttons"] = _bot_buttons.get((site, bot_id), {}) if bot_id else {}
                out.append({
                    **seat_data,
                    "pending_cmd": pending_cmd,
                    "bot_id": bot_id,
                })
            else:
                # Villain (face-down cards): treat as empty — only self-players shown
                out.append({
                    "seat_no":    seat_no,
                    "name":       None,
                    "stack_zar":  0,
                    "hole_cards": [],
                    "status":     "empty",
                    "is_dealer":  False,
                    "is_hero":    False,
                    "is_self_player": False,
                    "last_seen":  None,
                    "pending_cmd": None,
                    "bot_id":     None,
                    "available_actions": [],
                })
        else:
            # Empty seat placeholder
            out.append({
                "seat_no":    seat_no,
                "name":       None,
                "stack_zar":  0,
                "hole_cards": [],
                "status":     "empty",
                "is_dealer":  False,
                "is_hero":    False,
                "last_seen":  None,
                "pending_cmd": None,
                "bot_id":     None,
            })
    return out


def _get_latest_collector_batch():
    """Fetch the latest raw collector batch (ONE table snapshot)."""
    try:
        candidates = list(_COLLECTOR_SAVE_DIR.glob('*.txt'))
        if not candidates:
            return None
        latest = max(candidates, key=lambda f: f.stat().st_mtime)
        return latest.read_text(encoding='utf-8').strip()
    except Exception as e:
        current_app.logger.warning(f'[COLLECTOR] Could not read batch: {e}')
        return None


def _sync_collector_batch_to_table(site, table_id):
    """
    V2: Sync latest collector batch into table state (site-scoped).
    Called after snapshot updates to keep raw_batch current.
    Returns True if batch was updated.
    """
    try:
        candidates = list(_COLLECTOR_SAVE_DIR.glob('*.txt'))
        if not candidates:
            return False

        latest = max(candidates, key=lambda f: f.stat().st_mtime)
        batch_content = latest.read_text(encoding='utf-8').strip()

        key = (site, table_id)
        if key in _tables:
            current_batch = _tables[key].get("raw_batch")
            if current_batch != batch_content:
                _tables[key]["raw_batch"] = batch_content
                current_app.logger.debug(f'[V2] Updated raw_batch for table={site}/{table_id}')
                return True
        return False
    except Exception as e:
        current_app.logger.warning(f'[V2] Could not sync collector batch: {e}')
        return False


def _sync_hero_cards_to_collector(table_id, table):
    """
    Feed all cached hero cards into the collector accumulator so the engine
    poller (/api/collector/latest) sees every hero's hand automatically.
    Called inside _store_lock after each snapshot update.
    """
    global _coll_accumulated_hands, _coll_board, _coll_last_update, _coll_source

    # Build hands list from all cached hero cards for this table, ordered by seat_no
    site = table.get("site")
    hero_entries = sorted(
        [(sno, cards) for (sid, tid, sno), cards in _hero_cards.items()
         if sid == site and tid == table_id and cards],
        key=lambda x: x[0]
    )
    if not hero_entries:
        return

    hands = [''.join(cards) for _, cards in hero_entries]

    # Build board string
    board = table.get("board", {})
    board_str = None
    flop = board.get("flop") or []
    if flop:
        board_str = ''.join(flop)
        turn = board.get("turn")
        if turn:
            board_str += turn
        river = board.get("river")
        if river:
            board_str += river

    with _coll_lock:
        _coll_accumulated_hands = hands
        _coll_board = board_str
        _coll_last_update = time.time()
        _coll_source = f'hero_merge_{table_id}'


def _table_view(table):
    return {
        "table_id":      table["table_id"],
        "site":          table.get("site"),
        "variant":       table["variant"],
        "street":        table["street"],
        "pot_zar":       table["pot_zar"],
        "dealer_seat":   table["dealer_seat"],
        "board":         table["board"],
        "state_version": table["state_version"],
        "last_updated":  table["last_ts"],
        "seats":         _build_seats_list(table),
        "collector_batch": _get_latest_collector_batch(),
    }

# ── P1: State persistence ──────────────────────────────────────────────────────

def _serialise_state():
    """Return a JSON-safe snapshot of _tables + auto-rules.
    Table keys are f'{site}::{table_id}' (double colon); auto-rules live under
    the reserved '_auto_rules' key so legacy single-key rows are ignored."""
    return {
        **{
            f"{site}::{tid}": {
                **{k: v for k, v in t.items() if k != "seats"},
                "seats": {
                    str(sno): seat
                    for sno, seat in t["seats"].items()
                }
            }
            for (site, tid), t in _tables.items()
        },
        "_auto_rules": {
            f"{site}::{tid}": rule
            for (site, tid), rule in _auto_rules.items()
        },
    }


def _load_state():
    """Load persisted state from disk into _tables + _auto_rules on startup.
    Only 'site::table_id' keys are loaded; legacy single-key rows are skipped."""
    if not STATE_FILE.exists():
        return
    try:
        raw = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        for key, t in raw.items():
            if key == "_auto_rules":
                for rk, rule in (t or {}).items():
                    if "::" in rk:
                        site, tid = rk.split("::", 1)
                        _auto_rules[(site, tid)] = rule
                continue
            if '::' not in key:
                continue  # legacy single-key JSON — ignored safely
            site, tid = key.split('::', 1)
            t["site"] = site
            t["table_id"] = tid
            t["seats"] = {int(k): v for k, v in t.get("seats", {}).items()}
            _tables[(site, tid)] = t
        current_app.logger.info(
            f"[PERSIST] Loaded {len(_tables)} table(s), {len(_auto_rules)} auto-rule(s) from {STATE_FILE}"
        )
    except Exception as e:
        current_app.logger.warning(f"[PERSIST] Could not load state: {e}")


def _write_state(snapshot) -> None:
    """Write the state snapshot to disk (tmp + atomic replace). No lock held."""
    tmp = STATE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(snapshot, default=str), encoding='utf-8')
    tmp.replace(STATE_FILE)


def _persist_now() -> None:
    """Synchronous persist (used by config writes; outside _store_lock)."""
    try:
        with _store_lock:
            snapshot = _serialise_state()
        _write_state(snapshot)
    except Exception as e:
        current_app.logger.warning(f"[PERSIST] Write failed: {e}")


def _persist_loop():
    """Background thread: snapshot state to disk every PERSIST_INT seconds."""
    while True:
        time.sleep(PERSIST_INT)
        try:
            with _store_lock:
                snapshot = _serialise_state()
            _write_state(snapshot)
        except Exception as e:
            current_app.logger.warning(f"[PERSIST] Write failed: {e}")

# ── P2: Stale seat eviction + command expiry ───────────────────────────────────

def _cleanup_loop():
    """Background thread: evict stale seats and expire old commands."""
    while True:
        time.sleep(10)
        now = time.time()
        try:
            with _store_lock:
                for table in list(_tables.values()):
                    site = table.get("site")
                    # Evict seats not seen recently
                    live = {
                        sno: seat for sno, seat in table["seats"].items()
                        if seat.get("last_seen") and (now - seat["last_seen"]) < SEAT_TTL
                    }
                    evicted_snos = set(table["seats"].keys()) - set(live.keys())
                    if evicted_snos:
                        # Clean up all associated state for evicted seats
                        for sno in evicted_snos:
                            seat_key = (site, table['table_id'], sno)
                            _hero_cards.pop(seat_key, None)
                            evicted_bot = _seat_bots.pop(seat_key, None)
                            if evicted_bot:
                                _bot_seats.pop(evicted_bot, None)
                                _bot_actions.pop((site, evicted_bot), None)
                                _bot_buttons.pop((site, evicted_bot), None)
                            tok = generate_seat_token(site, table['table_id'], sno)
                            _command_queue.pop(tok, None)
                            _cashout_state.pop(tok, None)
                        table["seats"] = live
                        current_app.logger.info(
                            f"[CLEANUP] table={site}/{table['table_id']} evicted {len(evicted_snos)} stale seat(s) + cleaned state"
                        )

                # Expire old commands
                expired = 0
                for token, cmd in list(_command_queue.items()):
                    if cmd and cmd.get("status") == "pending":
                        age = now - cmd.get("queued_at", now)
                        if age > CMD_TTL:
                            _command_queue[token] = None
                            expired += 1
                if expired:
                    current_app.logger.info(f"[CLEANUP] Expired {expired} stale command(s)")

                # Remove empty tables (no seats, last update > 5 min ago)
                stale_tables = [
                    key for key, t in _tables.items()
                    if not t["seats"] and (now - t["last_ts"]) > 300
                ]
                for key in stale_tables:
                    del _tables[key]
                    current_app.logger.info(f"[CLEANUP] Removed empty table {key}")

        except Exception as e:
            current_app.logger.warning(f"[CLEANUP] Error: {e}")

# ── Endpoint 1: POST /api/snapshot ────────────────────────────────────────────

@remote_bp.route('/api/snapshot', methods=['POST'])
@limiter.limit("300 per minute")   # 5/sec — supports 6 heroes each at 1.5s intervals
def post_snapshot():
    api_key = request.headers.get('X-API-Key')
    if api_key != TRACKER_API_KEY:
        return jsonify({'ok': False, 'error': 'Invalid API key'}), 401

    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    # Site tenancy: extension sends 'site' ('pokerbet' | 'sunbet'); old builds
    # don't — default to 'pokerbet' for backward compatibility.
    site = payload.get('site') or 'pokerbet'

    table_id = payload.get('table_id')
    if not table_id:
        return jsonify({'ok': False, 'error': 'Missing table_id'}), 400

    seats_raw = payload.get('seats', [])
    hero_seat = next((s for s in seats_raw if s.get('is_hero')), None)
    if not hero_seat:
        return jsonify({'ok': False, 'error': 'No hero seat found'}), 400

    # Extract bot identity (hero player name from w4p.js)
    bot_id = payload.get('bot_id')

    ts = time.time()
    cashout_cmd = None   # built outside lock, queued inside

    with _store_lock:
        table = get_or_create_table(site, table_id)

        if ts < table["last_ts"]:
            return jsonify({'ok': True, 'ignored': 'stale'}), 200

        hand_key = make_hand_key(payload)
        if table["hand_key"] != hand_key:
            # Archive previous hand before resetting
            if table["hand_key"] is not None:
                _archive_hand(table)
            table["hand_key"]     = hand_key
            table["seat_map"]     = {}
            table["seats"]        = {}
            table["next_seat_no"] = 1
            table["raw_batch"]    = None  # V2: Clear stale batch on hand reset
            # Clear cached hero cards for this table (site-scoped)
            stale_keys = [k for k in _hero_cards if k[0] == site and k[1] == table_id]
            for k in stale_keys:
                del _hero_cards[k]
            # Clear bot-seat mappings for this table (site-scoped)
            stale_bots = [k for k in _seat_bots if k[0] == site and k[1] == table_id]
            for k in stale_bots:
                del _seat_bots[k]
            # Flush pending commands + cashout state on hand reset
            for sn in range(1, 10):
                t = generate_seat_token(site, table_id, sn)
                if t in _command_queue:
                    _command_queue[t] = None
                if t in _cashout_state:
                    del _cashout_state[t]
            current_app.logger.info(f'[V2] Hand reset: cleared batch/commands/cashout table={site}/{table_id}')

        table["street"]      = payload.get("street")
        table["pot_zar"]     = payload.get("pot_zar")
        table["board"]       = payload.get("board", {"flop": [], "turn": None, "river": None})
        table["variant"]     = payload.get("variant", "plo")
        table["dealer_seat"] = payload.get("dealer_seat")

        new_seats    = {}
        hero_seat_no = None

        # Prune stale seat_map entries: keep only names currently in seats
        active_names = set()
        for existing_sno, existing_seat in table.get("seats", {}).items():
            n = normalize_name(existing_seat.get("name"))
            if n: active_names.add(n)
        for s in seats_raw:
            n = normalize_name(s.get("name"))
            if n: active_names.add(n)
        stale = [k for k in table["seat_map"] if k not in active_names]
        for k in stale:
            del table["seat_map"][k]
        if stale:
            table["next_seat_no"] = max(table["seat_map"].values(), default=0) + 1

        for s in seats_raw:
            name_key = normalize_name(s.get("name")) or f"anon_{s.get('seat_index', id(s))}"
            if name_key not in table["seat_map"]:
                used = set(table["seat_map"].values())
                assigned = next((n for n in range(1, 10) if n not in used), table["next_seat_no"])
                table["seat_map"][name_key] = assigned
                table["next_seat_no"] = max(table["next_seat_no"], assigned + 1)



            seat_no = table["seat_map"][name_key]
            new_seats[seat_no] = {
                "seat_no":    seat_no,
                "name":       s.get("name"),
                "stack_zar":  s.get("stack_zar"),
                "hole_cards": s.get("hole_cards", []),
                "status":     s.get("status", "empty"),
                "is_dealer":  s.get("is_dealer", False),
                "is_hero":    s.get("is_hero", False),
                "last_seen":  ts,
            }
            if s.get("is_hero"):
                hero_seat_no = seat_no

        # Merge seats: protect other bots' data (hole_cards, is_hero) from overwrite
        for sno, sdata in new_seats.items():
            existing_bot = _seat_bots.get((site, table_id, sno))
            if existing_bot and bot_id and existing_bot != bot_id:
                # Seat owned by a different bot — update metadata only
                existing = table["seats"].get(sno)
                if existing:
                    existing["stack_zar"] = sdata.get("stack_zar", existing.get("stack_zar"))
                    existing["status"] = sdata.get("status", existing.get("status"))
                    existing["is_dealer"] = sdata.get("is_dealer", existing.get("is_dealer"))
                    existing["last_seen"] = sdata["last_seen"]
                else:
                    table["seats"][sno] = sdata
            else:
                table["seats"][sno] = sdata
        table["last_ts"]       = ts
        table["state_version"] += 1

        # ── Multi-hero: always cache hero cards, bot mapping when bot_id present ──
        if hero_seat_no is not None:
            hero_hc = hero_seat.get('hole_cards', [])
            if hero_hc:
                _hero_cards[(site, table_id, hero_seat_no)] = hero_hc
            if bot_id:
                update_bot_seat_mapping(bot_id, site, table_id, hero_seat_no)
                avail_actions = payload.get('available_actions', [])
                _bot_actions[(site, bot_id)] = avail_actions
                buttons = payload.get('buttons')
                if buttons:
                    _bot_buttons[(site, bot_id)] = buttons

        # V2: Sync latest collector batch into table state
        _sync_collector_batch_to_table(site, table_id)

        token = generate_seat_token(site, table_id, hero_seat_no)

        # ── Feed hero hands into collector accumulator for engine ──
        _sync_hero_cards_to_collector(table_id, table)

        # Cashout auto-trigger
        if token in _cashout_state:
            cashout_available = payload.get('cashout_available', False)
            _cashout_state[token]['available'] = cashout_available
            if _cashout_state[token]['requested'] and cashout_available:
                cashout_cmd = {
                    'id':        str(uuid.uuid4())[:8],
                    'type':      'cashout',
                    'amount':    None,
                    'queued_at': ts,
                    'status':    'pending',
                }
                _command_queue[token]              = cashout_cmd
                _cashout_state[token]['requested'] = False

        # ── Auto-action trigger (slice 7): hero on turn + rule active → queue ──
        rule = _auto_rules.get((site, table_id), "off")
        if rule != "off":
            actions = payload.get("available_actions") or []
            cmd = auto_actions.decide(rule, actions)
            if cmd:
                existing = _command_queue.get(token)
                if not (existing and existing.get("status") == "pending"):
                    auto_cmd = {
                        'id':        str(uuid.uuid4())[:8],
                        **cmd,
                        'queued_at': ts,
                        'status':    'pending',
                        'source':    'auto',
                    }
                    _command_queue[token] = auto_cmd
                    current_app.logger.info(
                        f"[AUTO] {rule} → {auto_cmd['type']} table={site}/{table_id} seat={hero_seat_no}"
                    )

    # Log outside lock
    if cashout_cmd:
        current_app.logger.info(f"[CASHOUT] Auto-queued table={site}/{table_id} seat_no={hero_seat_no}")

    _notify_sse()  # slice 6: push new state to SSE subscribers

    return jsonify({
        'ok':         True,
        'seat_token': token,
        'seat_no':    hero_seat_no,
        'table_id':   table_id,
        'site':       site,
    })

# ── Endpoint: auto-rules (slice 7) ────────────────────────────────────────────

@remote_bp.route('/api/auto-rules', methods=['GET'])
def get_auto_rules():
    with _store_lock:
        rules = {
            f"{site}/{tid}": rule
            for (site, tid), rule in _auto_rules.items()
        }
    return jsonify({'ok': True, 'rules': rules})


@remote_bp.route('/api/auto-rules/<site>/<table_id>', methods=['PUT'])
def put_auto_rule(site, table_id):
    payload = request.get_json(silent=True) or {}
    try:
        rule = auto_actions.validate_rule(payload.get('rule'))
    except auto_actions.AutoActionError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    with _store_lock:
        _auto_rules[(site, table_id)] = rule
    _persist_now()
    _notify_sse()
    return jsonify({'ok': True, 'site': site, 'table_id': table_id, 'rule': rule})

# ── Endpoint 2: GET /api/commands/pending ─────────────────────────────────────

@remote_bp.route('/api/commands/pending', methods=['GET'])
def get_pending_command():
    token = request.args.get('token')
    bot_id = request.args.get('bot_id')
    if not token and not bot_id:
        return jsonify({'ok': False, 'error': 'Missing token or bot_id'}), 400

    with _store_lock:
        # If bot_id provided (from bot containers), scan all pending commands
        if bot_id and not token:
            for qtoken, cmd in list(_command_queue.items()):
                if cmd and cmd.get('status') == 'pending':
                    cmd['_token'] = qtoken  # include token so bot can ack
                    return jsonify({'ok': True, 'command': cmd})
            return jsonify({'ok': True, 'command': None})

        cmd = _command_queue.get(token)
        if cmd and cmd.get('status') == 'pending':
            return jsonify({'ok': True, 'command': cmd})
        return jsonify({'ok': True, 'command': None})

# ── Endpoint 3: POST /api/commands/ack ────────────────────────────────────────

@remote_bp.route('/api/commands/ack', methods=['POST'])
def ack_command():
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    token      = payload.get('token')
    command_id = payload.get('command_id')
    if not token or not command_id:
        return jsonify({'ok': False, 'error': 'Missing token or command_id'}), 400

    with _store_lock:
        cmd = _command_queue.get(token)
        if cmd and cmd.get('id') == command_id:
            cmd['status'] = 'acked'
            _command_queue[token] = None
            current_app.logger.info(f"[CMD] Acked command {command_id}")

    return jsonify({'ok': True})

# ── Endpoint 4: POST /api/commands/queue ──────────────────────────────────────

@remote_bp.route('/api/commands/queue', methods=['POST'])
def queue_command():
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    site         = payload.get('site') or 'pokerbet'   # backward compat: default tenant
    table_id     = payload.get('table_id')
    command_type = payload.get('command_type')
    amount       = payload.get('amount')
    seat_no      = payload.get('seat_no')
    if seat_no is None:
        seat_no = payload.get('seat_index')

    if not all([table_id, seat_no is not None, command_type]):
        return jsonify({'ok': False, 'error': 'Missing required fields'}), 400

    token = generate_seat_token(site, table_id, seat_no)

    with _store_lock:
        table = _tables.get((site, table_id))
        if not table:
            return jsonify({'ok': False, 'error': 'Table not found'}), 404
        if int(seat_no) not in table["seats"]:
            return jsonify({'ok': False, 'error': 'Seat not connected'}), 404

        command_id = str(uuid.uuid4())[:8]
        _command_queue[token] = {
            'id':        command_id,
            'type':      command_type,
            'amount':    amount,
            'queued_at': time.time(),
            'status':    'pending',
        }

    current_app.logger.info(f"[CMD] Queued {command_type} cmd={command_id} table={site}/{table_id} seat={seat_no}")
    _notify_sse()  # slice 6: push pending-cmd state change
    return jsonify({'ok': True, 'command_id': command_id})

# ── Endpoint 4b: POST /api/actions/report ─────────────────────────────────────

@remote_bp.route('/api/actions/report', methods=['POST'])
def report_actions():
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400
    bot_id = payload.get('bot_id')
    actions = payload.get('available_actions', [])
    if not bot_id:
        return jsonify({'ok': False, 'error': 'Missing bot_id'}), 400
    site = payload.get('site') or 'pokerbet'   # backward compat: default tenant
    _bot_actions[(site, bot_id)] = actions
    buttons = payload.get('buttons')
    if buttons:
        _bot_buttons[(site, bot_id)] = buttons
    return jsonify({'ok': True})

# ── Endpoint 5: GET /api/table/<table_id> ─────────────────────────────────────

@remote_bp.route('/api/table/<table_id>', methods=['GET'])
def get_table(table_id):
    # Tenant scoping via ?site= query param (additive; default 'pokerbet')
    site = request.args.get('site') or 'pokerbet'
    with _store_lock:
        if table_id == 'latest':
            if not _tables:
                return jsonify({'ok': False, 'error': 'No active tables'}), 404
            table = max(_tables.values(), key=lambda t: t['last_ts'])
        else:
            table = _tables.get((site, table_id))
            if not table:
                return jsonify({'ok': False, 'error': 'Table not found'}), 404
        view = _table_view(table)
    return jsonify({'ok': True, 'table': view})

# ── Endpoint: GET /api/table/latest ───────────────────────────────────────────

# ── Endpoint: GET /api/table/latest (LONG POLLING) ───────────────────────────

@remote_bp.route('/api/table/latest', methods=['GET'])
def table_latest():
    global _last_good_view

    # Optional tenant filter: ?site=sunbet → latest within that tenant only.
    # Omitted → latest across ALL tenants (legacy behaviour).
    site = request.args.get('site') or None

    def _latest_table():
        if site:
            cands = [t for (s, _tid), t in _tables.items() if s == site]
        else:
            cands = list(_tables.values())
        return max(cands, key=lambda t: t['last_ts']) if cands else None

    # Long polling support - wait for changes
    timeout = int(request.args.get('timeout', 0))  # 0 = no wait (backward compatible)
    max_timeout = 25  # Max 25 seconds

    if timeout > 0:
        timeout = min(timeout, max_timeout)
        start_time = time.time()
        last_ts_seen = float(request.args.get('last_ts', 0))

        # Wait for new data or timeout
        while (time.time() - start_time) < timeout:
            with _store_lock:
                table = _latest_table()
                if table and table['last_ts'] > last_ts_seen:
                    # New data available!
                    view = _table_view(table)
                    return jsonify({'ok': True, 'table': view, 'long_poll': True})

            # Sleep briefly before checking again (don't spin-lock)
            time.sleep(0.05)  # Check every 50ms

        # Timeout reached - return current state anyway
        current_app.logger.debug('[LONGPOLL] Timeout reached, returning current state')

    # Regular polling or timeout - return current state
    now = time.time()

    with _store_lock:
        table = _latest_table()
        if not table:
            # No tables at all — use last-known-good if recent enough
            if _last_good_view and (now - _last_good_view['ts']) < _STALE_MAX_AGE:
                age_ms = int((now - _last_good_view['ts']) * 1000)
                return jsonify({
                    'ok': True,
                    'table': _last_good_view['view'],
                    'stale': True,
                    'age_ms': age_ms,
                    'source': 'last_known_good',
                    'long_poll': False
                })
            # Truly no data and no recent cache
            return jsonify({
                'ok': True,
                'table': {
                    'table_id': 'waiting',
                    'site':     site or 'pokerbet',
                    'street':   'WAITING',
                    'pot_zar':  0,
                    'board':    {'flop': [], 'turn': None, 'river': None},
                    'seats': [
                        {
                            'seat_no': i, 'name': None, 'stack_zar': 0,
                            'hole_cards': [], 'status': 'empty',
                            'is_dealer': False, 'is_hero': False,
                            'last_seen': None, 'pending_cmd': None,
                        }
                        for i in range(1, 10)
                    ],
                    'collector_batch': _get_latest_collector_batch()
                },
                'long_poll': False
            })

        view = _table_view(table)

        # Determine if this is a "good" view (has at least one occupied seat)
        occupied = [s for s in view.get('seats', []) if s.get('name')]
        if occupied:
            # Fresh, valid state — update cache
            _last_good_view = {'view': view, 'ts': now}
        elif _last_good_view and (now - _last_good_view['ts']) < _STALE_MAX_AGE:
            # Current state is partial/empty but we have recent good data
            age_ms = int((now - _last_good_view['ts']) * 1000)
            return jsonify({
                'ok': True,
                'table': _last_good_view['view'],
                'stale': True,
                'age_ms': age_ms,
                'source': 'last_known_good',
                'long_poll': False
            })

    return jsonify({'ok': True, 'table': view, 'long_poll': False})



# ── Endpoint 6: GET /api/tables ───────────────────────────────────────────────

@remote_bp.route('/api/tables', methods=['GET'])
def list_tables():
    with _store_lock:
        tables = sorted(
            [_table_view(t) for t in _tables.values()],
            key=lambda t: t['last_updated'],
            reverse=True,
        )
    return jsonify({'ok': True, 'tables': tables})

# ── Endpoint 7: GET /api/health ───────────────────────────────────────────────

@remote_bp.route('/api/health', methods=['GET'])
def health():
    with _store_lock:
        n_tables = len(_tables)
        n_cmds   = sum(1 for c in _command_queue.values() if c and c.get('status') == 'pending')
    return jsonify({
        'ok':           True,
        'environment':  os.getenv('FLASK_ENV', 'production'),
        'version':      'remote-control-3.0',
        'timestamp':    datetime.utcnow().isoformat(),
        'active_tables': n_tables,
        'pending_cmds':  n_cmds,
    })


@remote_bp.route('/api/bots', methods=['GET'])
def get_bots():
    """
    Return all known bots with their seating status.
    Used by Bots Manager page.
    """
    with _store_lock:
        bots = []

        # Add all bots that have sent snapshots
        for bot_id, info in _bot_seats.items():
            last_seen_ago = time.time() - info["last_seen"]
            state = "running" if last_seen_ago < 30 else "stale"

            seat = info.get("seat_no", info.get("seat_index"))
            bots.append({
                "name": bot_id,
                "site": info.get("site"),
                "table_id": info["table_id"],
                "seat_index": seat,
                "last_seen": info["last_seen"],
                "last_seen_ago": last_seen_ago,
                "state": state,
                "status": f"Seated at {info['table_id']} seat {seat}"
            })

        # Add known containers that haven't sent snapshots yet
        for i in range(1, 10):
            bot_id = f"pokerbet-bot{i}"
            if bot_id not in _bot_seats:
                bots.append({
                    "name": bot_id,
                    "site": "pokerbet",
                    "table_id": None,
                    "seat_index": None,
                    "last_seen": None,
                    "last_seen_ago": None,
                    "state": "unknown",
                    "status": "Not seated or not running"
                })

    return jsonify({"ok": True, "bots": bots})




# ══════════════════════════════════════════════════════════════════════════════
# Add this after the /api/health endpoint (around line 480)

@remote_bp.route('/api/status', methods=['GET'])
def status():
    """Detailed status endpoint with metrics"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        uptime_seconds = time.time() - process.create_time()
    except Exception:
        memory_mb = 0
        uptime_seconds = 0
    
    with _store_lock:
        table_count = len(_tables)
        command_queue_size = sum(1 for c in _command_queue.values() if c and c.get('status') == 'pending')
        # Count total seats across all tables
        total_seats = sum(len(t.get('seats', {})) for t in _tables.values())
    
    return jsonify({
        'service': 'remote-control-api',
        'status': 'healthy',
        'version': 'remote-control-3.0',
        'uptime_seconds': uptime_seconds,
        'timestamp': time.time(),
        'memory_mb': round(memory_mb, 2),
        'table_count': table_count,
        'seat_count': total_seats,
        'command_queue_size': command_queue_size,
        'warning_count': 0,
        'error_count': 0,
        'warnings': [],
        'errors': []
    })


@remote_bp.route('/api/version', methods=['GET'])
def version():
    """Version endpoint"""
    return jsonify({
        'service': 'remote-control-api',
        'version': 'remote-control-3.0',
        'build': os.getenv('FLASK_ENV', 'production'),
        'timestamp': time.time()
    })
# ██  HAND HISTORY (multi-hand ASCII log)
# ══════════════════════════════════════════════════════════════════════════════

@remote_bp.route('/api/hands/recent', methods=['GET'])
def hands_recent():
    """Return last N hands as ASCII text blocks.
    Each hand: hole cards, flop, turn, river (one line per street, cards only).
    Hands separated by '------------------------'."""
    limit = min(int(request.args.get('limit', 20)), HAND_HISTORY_MAX)
    with _hand_lock:
        hands = list(_hand_history[-limit:])
    return jsonify({
        'ok': True,
        'hands': hands,
        'count': len(hands),
    })


@remote_bp.route('/api/hands/clear', methods=['POST'])
def hands_clear():
    """Clear hand history."""
    with _hand_lock:
        _hand_history.clear()
    return jsonify({'ok': True})


# ██  HAND COLLECTOR
# ══════════════════════════════════════════════════════════════════════════════

from . import config as _cfg
VALIDATED_HANDS_DIR = Path(str(_cfg.COLLECTOR_DIR / 'validated_hands'))
VALIDATED_HANDS_DIR.mkdir(parents=True, exist_ok=True)
_COLLECTOR_HTML     = Path(str(_cfg.COLLECTOR_DIR / 'index.html'))
_COLLECTOR_SAVE_DIR = Path(str(_cfg.SAVE_DIR))
_COLLECTOR_SAVE_DIR.mkdir(parents=True, exist_ok=True)
# GoldRush collector save dir (same location /api/goldrush/save writes to)
_COLLECTOR_SAVE_DIR_GOLDRUSH = Path(str(_cfg.COLLECTOR_DIR / 'goldrush_collector' / 'saved_hands'))
_COLLECTOR_SAVE_DIR_GOLDRUSH.mkdir(parents=True, exist_ok=True)

# ── Collector hand accumulator ──────────────────────────────────────────────
# Accumulates unique hands across snapshots within a deal window.
# Each snapshot from n4p.js may only contain currently-visible hands (1-3),
# so we merge them into one complete batch.
import threading as _coll_threading, time as _coll_time
_coll_lock = _coll_threading.Lock()
_coll_accumulated_hands = []   # ordered unique hands
_coll_board = None             # latest board string
_coll_last_update = 0          # epoch of last snapshot
_coll_source = ''              # last writer identity
_COLL_WINDOW_SECONDS = 10      # reset accumulator after this idle gap
_coll_last_written = ""        # content hash for write gate
_coll_deal_file = None         # Path to current deal file (overwrite mode)


@remote_bp.route('/collector')
@remote_bp.route('/collector/')
def collector_ui():
    if _COLLECTOR_HTML.exists():
        return send_file(str(_COLLECTOR_HTML), mimetype='text/html')
    return '<h2>Hand Collector UI not found at ' + str(_COLLECTOR_HTML) + '</h2>', 404


@remote_bp.route('/collector/save', methods=['POST'])
def collector_save():
    global _coll_accumulated_hands, _coll_board, _coll_last_update, _coll_last_written, _coll_deal_file
    try:
        body = request.get_json(force=True) or {}
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    raw_text = (body.get('text') or '').strip()
    if not raw_text:
        return jsonify({'error': 'Empty text'}), 400

    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    if not lines:
        return jsonify({'error': 'Empty text'}), 400

    # Separate hands from board — BOARD: tag is the required protocol
    incoming_hands = []
    incoming_board = None
    source = (body.get('source') or '').strip()
    tagged = [l for l in lines if l.startswith('BOARD:')]
    if tagged:
        board_str = tagged[0][6:]  # strip 'BOARD:' prefix
        # Validate board: must be even-length card string (6, 8, or 10 chars)
        if len(board_str) in (6, 8, 10) and len(board_str) % 2 == 0:
            incoming_board = board_str
        else:
            current_app.logger.warning('[COLLECTOR] invalid board length %d: %s', len(board_str), board_str[:20])
        lines = [l for l in lines if not l.startswith('BOARD:')]
        incoming_hands = list(lines)
    else:
        # No BOARD: tag — all lines are hands, no board guessing
        current_app.logger.warning('[COLLECTOR] untagged payload (%d lines, source=%s) — board will not be extracted', len(lines), source or 'unknown')
        incoming_hands = list(lines)

    now = _coll_time.time()
    dup = False

    with _coll_lock:
        # Reset accumulator if idle gap exceeded (new deal)
        gap = now - _coll_last_update
        current_app.logger.info("[RESET-CHECK] gap=%.2f, threshold=%d, will_reset=%s", gap, _COLL_WINDOW_SECONDS, gap > _COLL_WINDOW_SECONDS)
        if now - _coll_last_update > _COLL_WINDOW_SECONDS:
            _coll_accumulated_hands = []
            _coll_board = None
            _coll_last_written = ""
            _coll_deal_file = None
            current_app.logger.info("[RESET] Cleared all state due to idle gap")

        _coll_last_update = now

        # Reject degraded snapshots: fewer hands than accumulated
        if _coll_accumulated_hands and len(incoming_hands) < len(_coll_accumulated_hands):
            return jsonify({'ok': True, 'dup': True, 'skipped': 'degraded_snapshot'}), 200

        # Detect deal change: overlapping cards = different deals
        # Skip overlap check if hands are identical (exact same snapshot)
        if _coll_accumulated_hands and incoming_hands and set(incoming_hands) != set(_coll_accumulated_hands):
            acc_cards = set()
            for h in _coll_accumulated_hands:
                for i in range(0, len(h) - 1, 2):
                    acc_cards.add(h[i:i+2].lower())
            has_overlap = False
            for h in incoming_hands:
                for i in range(0, len(h) - 1, 2):
                    if h[i:i+2].lower() in acc_cards:
                        has_overlap = True
                        break
                if has_overlap:
                    break
            if has_overlap:
                if len(incoming_hands) >= len(_coll_accumulated_hands):
                    # Incoming is larger or equal = new deal, replace accumulator
                    # BUT keep _coll_deal_file so we overwrite the same file
                    _coll_accumulated_hands = []
                    _coll_board = None
                    _coll_last_written = ""
                    # Note: Do NOT reset _coll_deal_file here - keep same file
                else:
                    # Accumulated is larger = incoming is stale, skip hands
                    # But still clear board if scraper reports no board (preflop/new deal)
                    if incoming_board is None:
                        _coll_board = None
                    return jsonify({'ok': True, 'dup': True, 'skipped': 'stale_batch'}), 200

        # Reject degraded snapshots: do not replace fuller set with smaller one
        if _coll_accumulated_hands and incoming_hands and len(incoming_hands) < len(_coll_accumulated_hands):
            return jsonify({'ok': True, 'dup': True, 'skipped': 'degraded_snapshot'}), 200

        # Accumulate unique hands (preserve order)
        before_count = len(_coll_accumulated_hands)
        existing_set = set(_coll_accumulated_hands)
        for hand in incoming_hands:
            if hand not in existing_set:
                _coll_accumulated_hands.append(hand)
                existing_set.add(hand)

        # Update board: set if present, clear if scraper reports no board
        if incoming_board:
            _coll_board = incoming_board
        else:
            _coll_board = None

        # Track writer source
        _coll_source = source

        dup = (len(_coll_accumulated_hands) == before_count and
               (incoming_board is None or incoming_board == _coll_board))

        # Build accumulated payload
        out_lines = list(_coll_accumulated_hands)
        if _coll_board:
            out_lines.append('BOARD:' + _coll_board)
        payload = '\n'.join(out_lines)

    # Write accumulated batch to disk (gated: only if content changed)
    current_app.logger.info("[DEDUP] payload len=%d, last_written len=%d, match=%s", len(payload), len(_coll_last_written), payload == _coll_last_written)
    if payload != _coll_last_written:
        if _coll_deal_file is None:
            ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
            _coll_deal_file = _COLLECTOR_SAVE_DIR / f'hand_{ts}.txt'
        _coll_deal_file.write_text(payload + '\n', encoding='utf-8')
        _coll_last_written = payload
        return jsonify({'ok': True, 'file': str(_coll_deal_file), 'dup': False}), 200
    else:
        return jsonify({'ok': True, 'file': str(_coll_deal_file) if _coll_deal_file else '', 'dup': True}), 200


@remote_bp.route("/collector/clear", methods=["POST"])
def collector_clear():
    """Reset the hand accumulator between dealing rounds."""
    global _coll_accumulated_hands, _coll_board, _coll_last_update, _coll_last_written, _coll_deal_file
    with _coll_lock:
        _coll_accumulated_hands = []
        _coll_board = None
        _coll_last_update = 0
        _coll_source = ''

    # Purge saved hand files so /api/collector/latest does not resurrect stale data
    purged = 0
    for f in _COLLECTOR_SAVE_DIR.glob("*.txt"):
        try:
            f.unlink()
            purged += 1
        except OSError:
            pass

    return jsonify({"ok": True, "message": f"Accumulator cleared, {purged} files purged"}), 200


@remote_bp.route('/collector/meta', methods=['GET'])
def collector_meta():
    return jsonify({'save_dir': str(_COLLECTOR_SAVE_DIR)}), 200



@remote_bp.route('/api/remote/status', methods=['GET'])
def remote_status():
    """Detailed remote control status with command queue and seat details"""
    now = time.time()
    
    with _store_lock:
        # Build command queue details
        command_details = []
        for token, cmd in _command_queue.items():
            if cmd and cmd.get('status') == 'pending':
                command_details.append({
                    'seat_token': token,
                    'command': cmd.get('command'),
                    'status': cmd.get('status'),
                    'queued_at': cmd.get('queued_at'),
                    'age_seconds': round(now - cmd.get('queued_at', now), 1) if cmd.get('queued_at') else 0,
                })
        
        # Sort by most recent
        command_details.sort(key=lambda c: c.get('queued_at', 0), reverse=True)
        
        # Build table details with seat info
        table_details = []
        for (site, table_id), table in _tables.items():
            seats_info = []
            for seat_no, seat in table.get('seats', {}).items():
                seat_token = seat.get('token', '')
                pending_cmd = _command_queue.get(seat_token)
                
                seats_info.append({
                    'seat_no': seat_no,
                    'name': seat.get('name'),
                    'stack_zar': seat.get('stack_zar', 0),
                    'status': seat.get('status', 'empty'),
                    'is_hero': seat.get('is_hero', False),
                    'is_dealer': seat.get('is_dealer', False),
                    'has_token': bool(seat_token),
                    'pending_command': pending_cmd.get('command') if pending_cmd and pending_cmd.get('status') == 'pending' else None,
                })
            
            table_details.append({
                'table_id': table_id,
                'site': site,
                'last_update': table.get('last_ts'),
                'age_seconds': round(now - table.get('last_ts', now), 1),
                'street': table.get('street', 'UNKNOWN'),
                'pot_zar': table.get('pot_zar', 0),
                'seat_count': len(table.get('seats', {})),
                'active_seats': sum(1 for s in seats_info if s['name'] or s['stack_zar'] > 0),
                'seats': seats_info,
            })
        
        # Sort tables by most recent activity
        table_details.sort(key=lambda t: t.get('last_update', 0), reverse=True)
        
        # Calculate stats
        total_tables = len(_tables)
        total_seats = sum(len(t.get('seats', {})) for t in _tables.values())
        active_commands = len(command_details)
        
    return jsonify({
        'service': 'remote-control',
        'status': 'healthy',
        'timestamp': now,
        'total_tables': total_tables,
        'total_seats': total_seats,
        'active_commands': active_commands,
        'commands': command_details[:20],  # Top 20 most recent
        'tables': table_details[:10],  # Top 10 most active tables with full details
    })

@remote_bp.route('/api/engine/status', methods=['GET'])
def engine_status():
    """Engine status endpoint - checks if equity engine is accessible"""
    engine_url = os.getenv('ENGINE_URL', 'http://127.0.0.1:3000')
    try:
        import requests
        response = requests.get(f'{engine_url}/api/health', timeout=2)
        if response.status_code == 200:
            engine_data = response.json()
            return jsonify({
                'service': 'equity-engine',
                'status': 'healthy',
                'engine_url': engine_url,
                'version': engine_data.get('version', 'unknown'),
                'timestamp': time.time(),
            })
        else:
            return jsonify({
                'service': 'equity-engine',
                'status': 'degraded',
                'engine_url': engine_url,
                'error': f'HTTP {response.status_code}',
                'timestamp': time.time(),
            })
    except Exception as e:
        return jsonify({
            'service': 'equity-engine',
            'status': 'offline',
            'engine_url': engine_url,
            'error': str(e),
            'timestamp': time.time(),
        })


@remote_bp.route('/api/collector/status', methods=['GET'])
def collector_status():
    """Collector/snapshot status endpoint with table activity metrics"""
    with _store_lock:
        tables_data = []
        now = time.time()
        
        for (site, table_id), table in _tables.items():
            last_update = table.get('last_ts', 0)
            age_seconds = now - last_update if last_update else 0
            
            # Count active (non-empty) seats
            active_seats = sum(1 for seat in table.get('seats', {}).values() 
                             if seat.get('name') or seat.get('stack_zar', 0) > 0)
            
            tables_data.append({
                'table_id': table_id,
                'site': site,
                'last_update': last_update,
                'age_seconds': round(age_seconds, 1),
                'street': table.get('street', 'UNKNOWN'),
                'seat_count': len(table.get('seats', {})),
                'active_seats': active_seats,
                'hand_key': table.get('hand_key', ''),
            })
        
        # Sort by most recent activity
        tables_data.sort(key=lambda t: t['last_update'], reverse=True)
        
        # Calculate overall stats
        total_tables = len(_tables)
        total_seats = sum(len(t.get('seats', {})) for t in _tables.values())
        active_tables = sum(1 for t in tables_data if t['age_seconds'] < 30)
        
    return jsonify({
        'service': 'collector',
        'status': 'healthy',
        'timestamp': now,
        'total_tables': total_tables,
        'active_tables': active_tables,  # Updated in last 30s
        'total_seats': total_seats,
        'tables': tables_data[:20],  # Return top 20 most recent
        'state_file': str(STATE_FILE),
    })
@remote_bp.route("/api/collector/latest", methods=["GET"])
def collector_latest():
    """Serve hands directly from in-memory accumulator (not files)."""
    import time as _time

    with _coll_lock:
        if not _coll_accumulated_hands:
            current_app.logger.info('[COLLECTOR] no_fresh_snapshot: accumulator empty')
            resp = make_response(jsonify({'ok': False, 'reason': 'no_fresh_snapshot'}), 200)
            resp.headers['X-Collector-Handler'] = 'patched-v1-empty'
            return resp

        # Stale data — no fresh snapshot within window
        if _coll_last_update and (_time.time() - _coll_last_update > 60):
            age = round(_time.time() - _coll_last_update)
            current_app.logger.info('[COLLECTOR] stale_snapshot: age=%ds', age)
            resp = make_response(jsonify({'ok': False, 'reason': 'stale_snapshot', 'age': age}), 200)
            resp.headers['X-Collector-Handler'] = 'patched-v1-stale'
            return resp

        out_lines = list(_coll_accumulated_hands)
        board = _coll_board

    raw_text = chr(10).join(out_lines)

    current_app.logger.info('[COLLECTOR] success: %d hands, board=%s, source=%s', len(out_lines), bool(board), _coll_source)
    resp = make_response(jsonify({'ok': True, 'raw': raw_text, 'board': board,
                    'hands': len(out_lines), 'source': _coll_source or 'unknown'}), 200)
    resp.headers['X-Collector-Handler'] = 'patched-v1-success'
    return resp

# ══════════════════════════════════════════════════════════════════════════════
# ██  CASHOUT
# ══════════════════════════════════════════════════════════════════════════════

@remote_bp.route('/api/cashout/request', methods=['POST'])
def request_cashout():
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    table_id = payload.get('table_id')
    seat_no  = payload.get('seat_no') or payload.get('seat_index')
    if not all([table_id, seat_no is not None]):
        return jsonify({'ok': False, 'error': 'Missing table_id or seat_no'}), 400

    site = payload.get('site') or 'pokerbet'   # backward compat: default tenant
    token = generate_seat_token(site, table_id, seat_no)

    with _store_lock:
        if token not in _cashout_state:
            _cashout_state[token] = {'requested': False, 'available': False}
        _cashout_state[token]['requested'] = True

    current_app.logger.info(f"[CASHOUT] Request queued table={site}/{table_id} seat_no={seat_no}")
    return jsonify({'ok': True, 'status': 'queued', 'seat_token': token})


@remote_bp.route('/api/cashout/status', methods=['GET'])
def cashout_status():
    token = request.args.get('token')
    if not token:
        return jsonify({'ok': False, 'error': 'Missing token'}), 400

    with _store_lock:
        state = _cashout_state.get(token, {'requested': False, 'available': False})

    return jsonify({'ok': True, 'state': state})



# ══════════════════════════════════════════════════════════════════════════════
# ██  AUTHENTICATION & AUTHORIZATION
# ══════════════════════════════════════════════════════════════════════════════

from flask_login import login_user, logout_user





# ══════════════════════════════════════════════════════════════════════════════
# ██  BATCH PARSER — table snapshot → players + board
# ══════════════════════════════════════════════════════════════════════════════

import re as _re
_CARD_RE = _re.compile(r'^([AKQJT2-9][shdc])+$')

def _valid_cards(line):
    """Check line is valid concatenated card tokens, even length, no dupes."""
    if not line or len(line) % 2 != 0 or len(line) < 6:
        return False
    if not _CARD_RE.match(line):
        return False
    cards = [line[i:i+2] for i in range(0, len(line), 2)]
    if len(cards) != len(set(cards)):
        return False  # duplicate card
    return True

def _parse_batch(lines):
    """Parse a batch of lines into players + board."""
    clean = []
    for l in lines:
        n = l.strip().replace(' ', '')
        if '|' in n:
            n = n.split('|')[0]  # strip legacy board
        if n and _valid_cards(n):
            clean.append(n)

    # Step 1: lock players (first <=9 lines of 8 chars)
    players = []
    leftovers = []
    for line in clean:
        if len(line) == 8 and len(players) < 9:
            players.append(line)
        else:
            leftovers.append(line)

    # Step 2: board candidates from leftovers
    # Collect all player cards for overlap check
    player_cards = set()
    for p in players:
        for i in range(0, len(p), 2):
            player_cards.add(p[i:i+2])

    # Filter candidates: valid, no overlap with players
    candidates = []
    for line in leftovers:
        if len(line) not in (6, 8, 10):
            continue
        board_cards = [line[i:i+2] for i in range(0, len(line), 2)]
        if any(c in player_cards for c in board_cards):
            continue  # overlap
        candidates.append(line)

    # Step 3: check prefix consistency, pick longest
    board = None
    if candidates:
        candidates.sort(key=len, reverse=True)
        for c in candidates:
            # verify shorter candidates are prefixes
            consistent = True
            for other in candidates:
                if len(other) < len(c) and c[:len(other)] != other:
                    consistent = False
                    break
            if consistent:
                board = c
                break
        if not board:
            board = candidates[0]  # fallback: longest

    # Step 4: derive streets
    flop = turn = river = None
    if board:
        if len(board) >= 6:
            flop = board[:6]
        if len(board) >= 8:
            turn = board[6:8]
        if len(board) == 10:
            river = board[8:10]

    return {
        'players': players,
        'player_count': len(players),
        'flop': flop,
        'turn': turn,
        'river': river,
        'board_raw': board,
        'partial': len(players) < 6,
    }

@remote_bp.route('/api/parse/batch', methods=['POST'])
def api_parse_batch():
    """Parse raw collector text into structured table snapshot."""
    body = request.get_json(force=True) or {}
    text = (body.get('text') or '').strip()
    if not text:
        return jsonify({'ok': False, 'error': 'empty'}), 400

    batches_raw = text.split('\n\n')
    results = []
    for batch_text in batches_raw:
        lines = [l for l in batch_text.strip().split('\n') if l.strip()]
        if lines:
            results.append(_parse_batch(lines))

    return jsonify({'ok': True, 'batches': results, 'count': len(results)}), 200

# ── Run ────────────────────────────────────────────────────────────────────────


# GoldRush API Routes (proper paths /api/goldrush/*)
@remote_bp.route("/api/goldrush/save", methods=["POST", "OPTIONS"])
def api_goldrush_save():
    """Save GoldRush batch - mirrors /api/collector/save"""
    if request.method == "OPTIONS":
        return "", 204
    
    data = request.get_json()
    text = data.get("text", "").strip()
    
    if not text:
        return jsonify({"ok": False, "error": "empty text"}), 400
    
    # Save to goldrush directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"goldrush_{ts}.txt"
    save_dir = str(_cfg.COLLECTOR_DIR / 'goldrush_collector' / 'saved_hands')
    os.makedirs(save_dir, exist_ok=True)
    filepath = os.path.join(save_dir, filename)
    
    # Check for duplicate
    duplicate = False
    files = sorted([f for f in os.listdir(save_dir) if f.endswith(".txt")])
    if files:
        last_file = os.path.join(save_dir, files[-1])
        with open(last_file, "r") as f:
            if f.read().strip() == text:
                duplicate = True
    
    if not duplicate:
        with open(filepath, "w") as f:
            f.write(text)
        current_app.logger.info(f"[GoldRush] Saved: {filename}")
    
    return jsonify({"ok": True, "file": filepath, "dup": duplicate, "timestamp": ts})

@remote_bp.route("/api/goldrush/latest", methods=["GET"])
def api_goldrush_latest():
    """Get latest GoldRush batch - mirrors /api/collector/latest"""
    try:
        save_dir = str(_cfg.COLLECTOR_DIR / 'goldrush_collector' / 'saved_hands')
        os.makedirs(save_dir, exist_ok=True)
        
        files = sorted([f for f in os.listdir(save_dir) if f.startswith("goldrush_") and f.endswith(".txt")])
        
        if not files:
            return jsonify({"ok": True, "raw": None, "file": None})
        
        latest_file = os.path.join(save_dir, files[-1])
        with open(latest_file, "r") as f:
            raw_batch = f.read()
        
        return jsonify({
            "ok": True,
            "raw": raw_batch,
            "file": latest_file,
            "timestamp": files[-1].replace("goldrush_", "").replace(".txt", "")
        })
    
    except Exception as e:
        current_app.logger.error(f"[GoldRush] Error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEMD SERVICE — recommended settings (P1 + P3 fixes)
# Update /etc/systemd/system/plo-equity.service:
#
# [Unit]
# Description=PLO Remote Table Control v3
# After=network.target
#
# [Service]
# User=plo
# WorkingDirectory=/opt/plo-equity
# EnvironmentFile=/opt/plo-equity/.env
# ExecStart=/opt/plo-equity/venv/bin/gunicorn \
#     -w 3 \
#     --timeout 60 \
#     --worker-class sync \
#     --bind 0.0.0.0:8080 \
#     app:app
# Restart=on-failure
# RestartSec=5
# StartLimitBurst=5
# StartLimitIntervalSec=60
# StandardOutput=journal
# StandardError=journal
#
# [Install]
# WantedBy=multi-user.target
# ══════════════════════════════════════════════════════════════════════════════

@remote_bp.route('/api/collector/save/goldrush', methods=['POST', 'OPTIONS'])
def collector_save_goldrush():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.get_json(force=True)
        raw_batch = data.get('batch', '').strip()
        if not raw_batch:
            return jsonify({'ok': False, 'error': 'empty batch'}), 400
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f'goldrush_hand_{ts}.txt'
        filepath = _COLLECTOR_SAVE_DIR_GOLDRUSH / filename
        filepath.write_text(raw_batch, encoding='utf-8')
        current_app.logger.info(f'[GoldRush] Saved collector batch: {filename} ({len(raw_batch)} chars)')
        return jsonify({'ok': True, 'file': str(filepath), 'size': len(raw_batch)})
    except Exception as e:
        current_app.logger.error(f'[GoldRush] Collector save error: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500

@remote_bp.route('/api/collector/latest/goldrush', methods=['GET'])
def collector_latest_goldrush():
    try:
        candidates = list(_COLLECTOR_SAVE_DIR_GOLDRUSH.glob('goldrush_hand_*.txt'))
        if not candidates:
            return jsonify({'ok': False, 'error': 'no batches found'}), 404
        latest = max(candidates, key=lambda f: f.stat().st_mtime)
        raw_batch = latest.read_text(encoding='utf-8').strip()
        return jsonify({'ok': True, 'raw': raw_batch, 'file': str(latest), 'timestamp': latest.stat().st_mtime})
    except Exception as e:
        current_app.logger.error(f'[GoldRush] Collector latest error: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500

@remote_bp.route('/api/table/latest/goldrush', methods=['GET'])
def table_latest_goldrush():
    try:
        # GoldRush is betconstruct → lives in the 'pokerbet' tenant
        site = 'pokerbet'
        with _store_lock:
            goldrush_tables = {
                tid: t for (s, tid), t in _tables.items()
                if s == site and str(tid).startswith('goldrush_')
            }
            if not goldrush_tables:
                return jsonify({'ok': False, 'error': 'no goldrush tables'}), 404
            latest_table_id = max(goldrush_tables.keys(),
                                  key=lambda tid: goldrush_tables[tid].get('last_ts', 0))
            table = goldrush_tables[latest_table_id]
        try:
            candidates = list(_COLLECTOR_SAVE_DIR_GOLDRUSH.glob('goldrush_hand_*.txt'))
            if candidates:
                latest_file = max(candidates, key=lambda f: f.stat().st_mtime)
                raw_batch = latest_file.read_text(encoding='utf-8').strip()
                table['raw_batch'] = raw_batch
        except Exception as e:
            current_app.logger.warning(f'[GoldRush] Could not sync collector batch: {e}')
        return jsonify({'ok': True, 'table': table, 'table_id': latest_table_id})
    except Exception as e:
        current_app.logger.error(f'[GoldRush] Table latest error: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500

@remote_bp.route('/api/snapshot/goldrush', methods=['POST'])
def snapshot_goldrush():
    try:
        data = request.get_json(force=True)
        table_id = data.get('table_id', 'goldrush_default')
        if not table_id.startswith('goldrush_'):
            table_id = f'goldrush_{table_id}'
        # GoldRush is betconstruct → pokerbet tenant (site tenancy)
        site = 'pokerbet'
        with _store_lock:
            table = get_or_create_table(site, table_id)
            if 'seats' in data:
                raw_seats = data['seats']
                if isinstance(raw_seats, list):
                    table['seats'] = {}
                    for i, s in enumerate(raw_seats):
                        if not isinstance(s, dict):
                            continue
                        sno = s.get('seat_no') or (i + 1)
                        s.setdefault('last_seen', time.time())  # survive seat TTL eviction
                        table['seats'][sno] = s
                elif isinstance(raw_seats, dict):
                    table['seats'] = raw_seats
            if 'board' in data:
                table['board'] = data['board']
            if 'pot' in data:
                table['pot_zar'] = data['pot']
            table['street'] = data.get('street', table.get('street'))
            table['last_ts'] = time.time()
            table['state_version'] += 1
        current_app.logger.info(f'[GoldRush] Snapshot updated: {site}/{table_id}')
        return jsonify({'ok': True, 'table_id': table_id})
    except Exception as e:
        current_app.logger.error(f'[GoldRush] Snapshot error: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Startup (called from run.py AFTER app exists; never at import) ──

def start_background(app):
    """Load persisted state + start daemon threads inside app context."""
    app.logger.setLevel(logging.INFO)
    with app.app_context():
        _load_state()
    for target, name in [(_persist_loop, 'state-persist'),
                         (_cleanup_loop, 'seat-cleanup')]:
        threading.Thread(target=lambda t=target: _run_in_ctx(app, t),
                        name=name, daemon=True).start()


def _run_in_ctx(app, target):
    with app.app_context():
        target()
