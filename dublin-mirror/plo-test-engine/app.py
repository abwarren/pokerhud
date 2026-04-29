#!/usr/bin/env python3
"""
PLO Remote Table Control - Flask Backend
Endpoints for snapshot collection, command queuing, and table merging
"""

import os
import sys
import time
import hmac
import hashlib
import threading
import uuid
import tempfile
import subprocess
import re
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from multiprocessing import cpu_count

# Import seating manager and poker clock
sys.path.insert(0, os.path.dirname(__file__))
from services.agent_seating_manager import AgentSeatingManager
from services.poker_clock import get_clock

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes (n4p.js runs on different domain)

# Register equity engine routes (SSE streaming for /api/run, /api/stream)
from equity_routes import register_equity_routes
register_equity_routes(app)

# Register collector routes (/api/collector/*)
from collector_routes import register_collector_routes
register_collector_routes(app)

# Register tournament blueprint
from tournament import tournament_bp
app.register_blueprint(tournament_bp)

# Environment variables
N4P_SEAT_SECRET = os.getenv('N4P_SEAT_SECRET', 'default_secret_change_me')
TRACKER_API_KEY = os.getenv('TRACKER_API_KEY', 'trk_default')

# In-memory data stores
_snapshot_store = {}  # key: "table_id:seat_index", value: seat record
_merged_tables = {}   # key: table_id, value: MergedTable dict
_command_queue = {}   # key: seat_token, value: command dict or None
_bot_states = {}      # key: bot_id, value: hero state dict
_control_states = {}  # key: table_id:seat_index, value: control availability dict
_store_lock = threading.Lock()

# Initialize seating manager
_seating_manager = AgentSeatingManager()

# Hand collection store - TIME-BASED GROUPING
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class HandBuffer:
    start_ts: float
    hole_cards: List[str] = field(default_factory=list)
    flop: List[str] = field(default_factory=list)
    turn: Optional[str] = None
    river: Optional[str] = None

_active_hand = None  # Current hand being built
_hand_history = []   # List of completed hand strings (max 50)
_hand_lock = threading.Lock()
_current_hand = {
    'hand_id': None,
    'status': 'cleared',
    'street': 'waiting',
    'raw_text': '',
    'updated_at': datetime.utcnow().isoformat()
}

def format_hand(hand: HandBuffer) -> str:
    """Format hand buffer as ASCII block - cards only, no labels"""
    lines = []

    # Line 1: hole cards
    if hand.hole_cards:
        lines.append(''.join(hand.hole_cards))

    # Line 2: flop
    if hand.flop:
        lines.append(''.join(hand.flop))

    # Line 3: turn
    if hand.turn:
        lines.append(hand.turn)

    # Line 4: river
    if hand.river:
        lines.append(hand.river)

    return '\n'.join(lines) + '\n------------------------\n'

def on_hole_card(card: str, ts: float):
    """Process hole card detection with 1-second grouping window"""
    global _active_hand

    if _active_hand is None:
        _active_hand = HandBuffer(start_ts=ts, hole_cards=[card])
        return

    if ts - _active_hand.start_ts <= 1.0:
        _active_hand.hole_cards.append(card)
    else:
        # Time window expired, start new hand
        _active_hand = HandBuffer(start_ts=ts, hole_cards=[card])

def on_board_cards(board_cards: List[str]):
    """Process board card detection (flop/turn/river)"""
    global _active_hand, _hand_history

    if _active_hand is None:
        return

    # Assign flop (first 3 cards)
    if len(board_cards) >= 3 and not _active_hand.flop:
        _active_hand.flop = board_cards[:3]

    # Assign turn (4th card)
    if len(board_cards) >= 4 and _active_hand.turn is None:
        _active_hand.turn = board_cards[3]

    # Assign river (5th card) and finalize hand
    if len(board_cards) >= 5 and _active_hand.river is None:
        _active_hand.river = board_cards[4]

        # Format and store completed hand
        hand_text = format_hand(_active_hand)
        _hand_history.append(hand_text)

        # Keep only last 50 hands
        if len(_hand_history) > 50:
            _hand_history.pop(0)

        # Clear active hand buffer
        _active_hand = None

# Helper: Generate deterministic seat token
def generate_seat_token(table_id, seat_index):
    """Generate HMAC-based seat token (deterministic per table+seat)"""
    msg = f"{table_id}:{seat_index}".encode('utf-8')
    return hmac.new(N4P_SEAT_SECRET.encode('utf-8'), msg, hashlib.sha256).hexdigest()

# Helper: Merge all seat snapshots for a table
def normalize_seats(seats):
    """
    CRITICAL: Normalize seat data to always return 9 seats (0-8).

    Input: Variable-length array (could be 1 seat, could be 5 seats)
    Output: Fixed 9-seat array with EMPTY seats filled in

    Mental model: Seats = STRUCTURE (fixed), Players = DATA (dynamic)
    """
    MAX_SEATS = 9
    seats_dict = {}

    # Step 1: Build seat map from provided seats
    for seat in seats:
        idx = seat.get('seat_index')
        if idx is not None:
            seats_dict[idx] = seat

    # Step 2: Fill in missing seats (0 to MAX_SEATS-1)
    for i in range(MAX_SEATS):
        if i not in seats_dict:
            seats_dict[i] = {
                'seat_index': i,
                'name': None,
                'stack_zar': None,
                'hole_cards': [],
                'cards_count': 0,
                'cards_visible': False,
                'is_hero': False,
                'is_dealer': False,
                'status': 'empty'
            }

    # Step 3: Return sorted array (0-8)
    return sorted(seats_dict.values(), key=lambda s: s['seat_index'])


def merge_table(table_id):
    """Build merged table view from all seat snapshots"""
    now = time.time()

    # Collect all seats for this table
    seat_records = []
    for store_key, record in _snapshot_store.items():
        if record['table_id'] == table_id:
            seat_records.append(record)

    if not seat_records:
        return None

    # Use most recent snapshot for table-level data
    latest_record = max(seat_records, key=lambda r: r['last_seen'])
    snap = latest_record['last_snapshot']

    # Build merged seats list
    seats_dict = {}
    for record in seat_records:
        seat_idx = record['seat_index']
        snap_seat = None

        # Find this seat in the snapshot
        for s in record['last_snapshot']['seats']:
            if s['seat_index'] == seat_idx:
                snap_seat = s
                break

        if snap_seat:
            # Check for pending command
            pending_cmd = None
            cmd = _command_queue.get(record['seat_token'])
            if cmd and cmd.get('status') == 'pending':
                pending_cmd = cmd['type']

            seats_dict[seat_idx] = {
                'seat_index': seat_idx,
                'name': snap_seat.get('name') or f"Seat {seat_idx}",
                'stack_zar': snap_seat.get('stack_zar'),
                'hole_cards': snap_seat.get('hole_cards', []),
                'status': snap_seat.get('status', 'empty'),
                'is_dealer': snap_seat.get('is_dealer', False),
                'is_hero': snap_seat.get('is_hero', False),
                'is_self_player': snap_seat.get('is_self_player', False),
                'available_actions': snap_seat.get('available_actions', []),
                'sitting_out': snap_seat.get('sitting_out', False),
                'has_token': True,
                'last_seen_ago': now - record['last_seen'],
                'pending_cmd': pending_cmd,
            }

    # Fill in empty seats from any snapshot (table structure)
    for s in snap.get('seats', []):
        if s['seat_index'] not in seats_dict:
            seats_dict[s['seat_index']] = {
                'seat_index': s['seat_index'],
                'name': s.get('name') or f"Seat {s['seat_index']}",
                'stack_zar': s.get('stack_zar'),
                'hole_cards': [],
                'status': s.get('status', 'empty'),
                'is_dealer': s.get('is_dealer', False),
                'has_token': False,
                'last_seen_ago': None,
                'pending_cmd': None,
            }

    # CRITICAL: Enforce 9-seat normalization
    # Always return all 9 seats (0-8), even if snapshot is missing seats
    MAX_SEATS = 9
    for i in range(MAX_SEATS):
        if i not in seats_dict:
            seats_dict[i] = {
                'seat_index': i,
                'name': f"Seat {i}",
                'stack_zar': None,
                'hole_cards': [],
                'status': 'empty',
                'is_dealer': False,
                'has_token': False,
                'last_seen_ago': None,
                'pending_cmd': None,
            }

    # Sort seats by index
    sorted_seats = sorted(seats_dict.values(), key=lambda s: s['seat_index'])

    merged = {
        'table_id': table_id,
        'variant': snap.get('variant', 'plo'),
        'street': snap.get('street', 'PREFLOP'),
        'pot_zar': snap.get('pot_zar'),
        'dealer_seat': snap.get('dealer_seat'),
        'board': snap.get('board', {'flop': [], 'turn': None, 'river': None}),
        'last_updated': now,
        'seats': sorted_seats,
    }

    return merged

# ============================================================================
# CORE API ENDPOINTS - Table Snapshots & Commands
# ============================================================================

# Endpoint 1: POST /api/snapshot
@app.route('/api/snapshot', methods=['POST'])
def post_snapshot():
    """Receive snapshot from player browser, return seat token"""

    # Auth check
    api_key = request.headers.get('X-API-Key')
    if api_key != TRACKER_API_KEY:
        return jsonify({'ok': False, 'error': 'Invalid API key'}), 401

    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    table_id = payload.get('table_id')
    seats = payload.get('seats', [])

    if not table_id:
        return jsonify({'ok': False, 'error': 'Missing table_id'}), 400

    # CRITICAL: Normalize seats to always have 9 seats before processing
    normalized_seats = normalize_seats(seats)
    payload['seats'] = normalized_seats

    # Find hero seat
    hero_seat = None
    for s in normalized_seats:
        if s.get('is_hero'):
            hero_seat = s
            break

    if not hero_seat:
        return jsonify({'ok': False, 'error': 'No hero seat found'}), 400

    seat_index = hero_seat['seat_index']
    store_key = f"{table_id}:{seat_index}"
    timestamp = time.time()

    with _store_lock:
        # Generate seat token
        token = generate_seat_token(table_id, seat_index)

        # Store/update seat record with normalized data
        _snapshot_store[store_key] = {
            'seat_token': token,
            'table_id': table_id,
            'seat_index': seat_index,
            'last_snapshot': payload,  # Now contains normalized 9 seats
            'last_seen': timestamp,
            'status': hero_seat.get('status', 'playing'),
            'name': hero_seat.get('name', f"Seat {seat_index}"),
            'stack_zar': hero_seat.get('stack_zar'),
        }

        # Rebuild merged table
        _merged_tables[table_id] = merge_table(table_id)

    return jsonify({
        'ok': True,
        'seat_token': token,
        'seat_index': seat_index,
        'table_id': table_id,
    })

# Endpoint 2: GET /api/commands/pending
@app.route('/api/commands/pending', methods=['GET'])
def get_pending_command():
    """Poll for pending commands (token-based auth)"""
    token = request.args.get('token')

    if not token:
        return jsonify({'ok': False, 'error': 'Missing token'}), 400

    with _store_lock:
        cmd = _command_queue.get(token)
        if cmd and cmd.get('status') == 'pending':
            return jsonify({'ok': True, 'command': cmd})
        else:
            return jsonify({'ok': True, 'command': None})

# Endpoint 3: POST /api/commands/ack
@app.route('/api/commands/ack', methods=['POST'])
def ack_command():
    """Acknowledge command execution"""
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    token = payload.get('token')
    command_id = payload.get('command_id')

    if not token or not command_id:
        return jsonify({'ok': False, 'error': 'Missing token or command_id'}), 400

    with _store_lock:
        cmd = _command_queue.get(token)
        if cmd and cmd.get('id') == command_id:
            cmd['status'] = 'acked'
            _command_queue[token] = None  # Clear after ack

    return jsonify({'ok': True})

# Endpoint 4: POST /api/commands/queue
@app.route('/api/commands/queue', methods=['POST'])
def queue_command():
    """Queue command from control panel"""
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    table_id = payload.get('table_id')
    seat_index = payload.get('seat_index')
    command_type = payload.get('command_type')

    if not all([table_id, seat_index is not None, command_type]):
        return jsonify({'ok': False, 'error': 'Missing required fields'}), 400

    # Generate token for this seat
    token = generate_seat_token(table_id, seat_index)
    store_key = f"{table_id}:{seat_index}"

    with _store_lock:
        # Check if seat exists
        if store_key not in _snapshot_store:
            return jsonify({'ok': False, 'error': 'Seat not connected'}), 404

        # Queue command
        command_id = str(uuid.uuid4())[:8]
        _command_queue[token] = {
            'id': command_id,
            'type': command_type,
            'queued_at': time.time(),
            'status': 'pending',
        }

        # Refresh merged table
        _merged_tables[table_id] = merge_table(table_id)

    return jsonify({'ok': True, 'command_id': command_id})

# Endpoint 5: GET /api/table/<table_id>
@app.route('/api/table/<table_id>', methods=['GET'])
def get_table(table_id):
    """Get merged table view"""
    with _store_lock:
        if table_id == 'latest':
            # Get most recently updated table
            if not _merged_tables:
                return jsonify({'ok': False, 'error': 'No active tables'}), 404
            table = max(_merged_tables.values(), key=lambda t: t['last_updated'])
        else:
            table = _merged_tables.get(table_id)
            if not table:
                return jsonify({'ok': False, 'error': 'Table not found'}), 404

    return jsonify({'ok': True, 'table': table})

# Endpoint 6: GET /api/tables
@app.route('/api/tables', methods=['GET'])
def list_tables():
    """List all active tables"""
    with _store_lock:
        tables = list(_merged_tables.values())
        tables.sort(key=lambda t: t['last_updated'], reverse=True)

    return jsonify({'ok': True, 'tables': tables})

# ============================================================================
# API ENDPOINTS (JSON responses only - STRICT /api/ prefix)
# ============================================================================

# Endpoint 7: GET /api/health
@app.route('/api/health', methods=['GET'])
def health():
    """Health check API"""
    return jsonify({
        'ok': True,
        'environment': os.getenv('FLASK_ENV', 'production'),
        'version': 'remote-control-3.0',
        'timestamp': datetime.utcnow().isoformat(),
    })

# ============================================================================
# UI ENDPOINTS (HTML responses only - NO /api/ prefix)
# ============================================================================

# Endpoint: GET / - Serve main dashboard
@app.route('/', methods=['GET'])
def dashboard():
    """Serve main remote control dashboard"""
    response = send_from_directory('/opt/plo-equity/static', 'index.html')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Endpoint: GET /equity - Serve equity dashboard
@app.route('/equity', methods=['GET'])
def equity_ui():
    """Serve equity dashboard HTML"""
    return send_from_directory('/opt/plo-equity/static', 'equity_dashboard.html')

# Endpoint: GET /remote - Serve hero bot remote control UI
@app.route('/remote', methods=['GET'])
def remote_ui():
    """Serve hero bot remote control HTML"""
    return send_from_directory('/opt/plo-equity/static', 'remote.html')

# Endpoint: GET /remotebutton - Serve W4P remote button control UI
@app.route('/remotebutton', methods=['GET'])
def remotebutton_ui():
    """Serve W4P remote button control HTML"""
    response = send_from_directory('/opt/plo-equity/static', 'remotebutton.html')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Endpoint: GET /clock - Serve poker clock UI
@app.route('/clock', methods=['GET'])
def clock_ui():
    """Serve poker clock HTML page"""
    return send_from_directory('/opt/plo-equity/static', 'poker_clock.html')

# Endpoint: GET /clock-tv - Serve poker clock TV display
@app.route('/clock-tv', methods=['GET'])
def clock_tv_ui():
    """Serve poker clock TV display HTML"""
    return send_from_directory('/opt/plo-equity/static', 'clock-tv.html')

# Endpoint: GET /debug - Serve debug dashboard
@app.route('/debug', methods=['GET'])
def debug_ui():
    """Serve debug dashboard HTML"""
    return send_from_directory('/opt/plo-equity/static', 'debug.html')

# TODO: Create these UI pages as needed:
# - /collector -> collector.html (hand collector UI)
# - /engine -> engine.html (engine dashboard)
# - /bots -> bots.html (bots management)
# - /workers -> workers.html (workers management)
# - /health -> health.html (system health dashboard)

# Endpoint: GET /loader - Serve N4P tracker loader page
@app.route('/loader', methods=['GET'])
def loader_ui():
    """Serve N4P tracker loader and bookmarklet page"""
    return send_from_directory('/opt/plo-equity/static', 'loader.html')

# Endpoint: GET /auto-inject - Serve auto-injection page
@app.route('/auto-inject', methods=['GET'])
def auto_inject_ui():
    """Serve N4P auto-injection testing page"""
    return send_from_directory('/opt/plo-equity/static', 'auto-inject.html')

# ============================================================================
# STATIC FILE ROUTES
# ============================================================================

# Endpoint: GET /n4p.js - Serve n4p tracker script
@app.route('/n4p.js', methods=['GET'])
def serve_n4p():
    """Serve n4p.js tracker script with no-cache headers"""
    response = send_from_directory('/opt/plo-equity/static', 'n4p.js', mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Tournament static file routes
@app.route('/static/tournament/<path:filename>', methods=['GET'])
def serve_tournament_static(filename):
    """Serve tournament static files"""
    return send_from_directory('/opt/plo-equity/static/tournament', filename)

# ============================================================================
# REMOTE CONTROL API ENDPOINTS - Bot State & Commands
# ============================================================================

# Endpoint: GET /api/remote-control/state/<bot_id> - Get hero bot state
@app.route('/api/remote-control/state/<bot_id>', methods=['GET'])
def get_bot_state(bot_id):
    """
    Get hero bot state according to API contract.
    Returns:
    {
      "ok": true,
      "state": {
        "hero_detected": boolean,
        "hero_seat": int | null,
        "hero_cards": string[],
        "board_cards": string[],
        "street": string,
        "seated": boolean,
        "in_hand": boolean,
        "can_act": boolean,
        "allowed_actions": string[],
        "waiting_for_big_blind": boolean
      }
    }
    """
    with _store_lock:
        state = _bot_states.get(bot_id)
        if not state:
            # Return default state when bot not detected
            return jsonify({
                'ok': True,
                'state': {
                    'hero_detected': False,
                    'hero_seat': None,
                    'hero_cards': [],
                    'board_cards': [],
                    'street': 'waiting',
                    'seated': False,
                    'in_hand': False,
                    'can_act': False,
                    'allowed_actions': [],
                    'waiting_for_big_blind': False
                }
            })

    return jsonify({'ok': True, 'state': state})

# Endpoint: POST /api/remote-control/command - Send command to bot
@app.route('/api/remote-control/command', methods=['POST'])
def send_bot_command():
    """
    Send command to bot.
    Payload:
    {
      "bot_id": "bot_1",
      "action": "fold" | "check" | "call" | "raise" | "allin"
    }
    """
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    bot_id = payload.get('bot_id')
    action = payload.get('action')

    if not bot_id or not action:
        return jsonify({'ok': False, 'error': 'Missing bot_id or action'}), 400

    # Validate action
    valid_actions = ['fold', 'check', 'call', 'raise', 'allin']
    if action not in valid_actions:
        return jsonify({'ok': False, 'error': f'Invalid action. Must be one of: {valid_actions}'}), 400

    # Check if bot exists
    with _store_lock:
        if bot_id not in _bot_states:
            return jsonify({'ok': False, 'error': 'Bot not found or not connected'}), 404

        state = _bot_states[bot_id]
        if not state.get('can_act'):
            return jsonify({'ok': False, 'error': 'Bot cannot act right now'}), 400

    # TODO: Agent 1 will implement command execution
    # For now, just log the command
    print(f"[REMOTE-CONTROL] Command received: bot={bot_id}, action={action}")

    return jsonify({'ok': True, 'message': f'Command {action} queued for {bot_id}'})

# Endpoint: POST /api/remote-control/update-state - Update bot state (for n4p.js)
@app.route('/api/remote-control/update-state', methods=['POST'])
def update_bot_state():
    """
    Update hero bot state (called by n4p.js).
    Payload matches API contract state structure.
    """
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    bot_id = payload.get('bot_id')
    if not bot_id:
        return jsonify({'ok': False, 'error': 'Missing bot_id'}), 400

    # Store the state
    with _store_lock:
        _bot_states[bot_id] = {
            'hero_detected': payload.get('hero_detected', False),
            'hero_seat': payload.get('hero_seat'),
            'hero_cards': payload.get('hero_cards', []),
            'board_cards': payload.get('board_cards', []),
            'street': payload.get('street', 'waiting'),
            'seated': payload.get('seated', False),
            'in_hand': payload.get('in_hand', False),
            'can_act': payload.get('can_act', False),
            'allowed_actions': payload.get('allowed_actions', []),
            'waiting_for_big_blind': payload.get('waiting_for_big_blind', False),
            'last_updated': time.time()
        }

    return jsonify({'ok': True})

# ============================================================================
# TABLE STATE API ENDPOINTS
# ============================================================================

# Endpoint: GET /api/state - Get table state with control availability and seating state
@app.route('/api/state', methods=['GET'])
def get_table_state():
    """
    Get complete table state including control availability and seating state machine.

    Query params:
    - agent_id: Optional agent ID to include seating state (e.g. "bot_1")

    Returns:
    {
      "ok": true,
      "table": {
        "max_players": 9,
        "seats": [...]
      },
      "hero": {
        "seated": boolean,
        "seat": int | null
      },
      "seating": {
        "agent_id": string | null,
        "current_state": string,
        "seated_confirmed": boolean,
        "buyin_dialog_open": boolean,
        "remote_control_ready": boolean,
        "table_open": boolean,
        "seat_index": int | null,
        "last_updated": float
      },
      "controls": {
        "buyin_confirm": {"visible": boolean, "enabled": boolean},
        "buyin_max": {"visible": boolean, "enabled": boolean},
        "buyin_min": {"visible": boolean, "enabled": boolean},
        "auto_buyin": {"visible": boolean, "enabled": boolean, "checked": boolean},
        "add_chips": {"visible": boolean, "enabled": boolean}
      }
    }
    """
    agent_id = request.args.get('agent_id')

    with _store_lock:
        # Get latest table
        if not _merged_tables:
            # Return empty state with explicit defaults
            return jsonify({
                'ok': True,
                'table': {
                    'max_players': 9,
                    'seats': []
                },
                'hero': {
                    'seated': False,
                    'seat': None
                },
                'seating': {
                    'agent_id': agent_id,
                    'current_state': 'IDLE',
                    'seated_confirmed': False,
                    'buyin_dialog_open': False,
                    'remote_control_ready': False,
                    'table_open': False,
                    'seat_index': None,
                    'last_updated': time.time()
                },
                'controls': {
                    'buyin_confirm': {'visible': False, 'enabled': False},
                    'buyin_max': {'visible': False, 'enabled': False},
                    'buyin_min': {'visible': False, 'enabled': False},
                    'auto_buyin': {'visible': False, 'enabled': False, 'checked': False},
                    'add_chips': {'visible': False, 'enabled': False}
                }
            })

        table = max(_merged_tables.values(), key=lambda t: t['last_updated'])

        # Find hero seat (seat with is_hero flag or first connected seat)
        hero_seat = None
        for seat in table['seats']:
            # Check if this is a connected seat (has_token=True)
            if seat.get('has_token'):
                hero_seat = seat['seat_index']
                break

        hero_seated = hero_seat is not None

        # Get agent seating state if agent_id provided
        seating_state = {
            'agent_id': agent_id,
            'current_state': 'IDLE',
            'seated_confirmed': False,
            'buyin_dialog_open': False,
            'remote_control_ready': False,
            'table_open': False,
            'seat_index': None,
            'last_updated': time.time()
        }

        if agent_id:
            agent = _seating_manager.get_agent_state(agent_id)
            if agent:
                # Map agent state to seating state
                current_state = agent.get('current_state', 'IDLE')
                seated_confirmed = agent.get('seated', False) and current_state in ['SEATED_CONFIRMED', 'ACTIVE']
                remote_control_ready = seated_confirmed and current_state == 'ACTIVE'

                seating_state = {
                    'agent_id': agent_id,
                    'current_state': current_state,
                    'seated_confirmed': seated_confirmed,
                    'buyin_dialog_open': agent.get('buyin_modal_visible', False),
                    'remote_control_ready': remote_control_ready,
                    'table_open': agent.get('table_open', False),
                    'seat_index': agent.get('seat_index'),
                    'last_updated': agent.get('last_updated', time.time())
                }

        # Get control states for hero seat
        control_key = f"{table['table_id']}:{hero_seat}" if hero_seat is not None else None
        controls = _control_states.get(control_key, {
            'buyin_confirm': {'visible': False, 'enabled': False},
            'buyin_max': {'visible': False, 'enabled': False},
            'buyin_min': {'visible': False, 'enabled': False},
            'auto_buyin': {'visible': False, 'enabled': False, 'checked': False},
            'add_chips': {'visible': hero_seated, 'enabled': hero_seated}  # ADD CHIPS always visible when seated
        })

        # Ensure ADD CHIPS is always available when seated
        if hero_seated:
            controls['add_chips'] = {'visible': True, 'enabled': True}

        return jsonify({
            'ok': True,
            'table': {
                'max_players': 9,
                'seats': table['seats']
            },
            'hero': {
                'seated': hero_seated,
                'seat': hero_seat
            },
            'seating': seating_state,
            'controls': controls
        })

# Endpoint: POST /api/state/update-controls - Update control availability (called by bot)
@app.route('/api/state/update-controls', methods=['POST'])
def update_control_states():
    """
    Update control availability from bot detection.

    Payload:
    {
      "table_id": "table_123",
      "seat_index": 4,
      "controls": {
        "buyin_confirm": {"visible": true, "enabled": true},
        "buyin_max": {"visible": true, "enabled": true},
        ...
      }
    }
    """
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    table_id = payload.get('table_id')
    seat_index = payload.get('seat_index')
    controls = payload.get('controls', {})

    if not table_id or seat_index is None:
        return jsonify({'ok': False, 'error': 'Missing table_id or seat_index'}), 400

    control_key = f"{table_id}:{seat_index}"

    with _store_lock:
        _control_states[control_key] = controls

    return jsonify({'ok': True})

# ============================================================================
# AGENT SEATING API ENDPOINTS
# ============================================================================

# Endpoint: GET /api/agent/seating/state/<agent_id> - Get agent seating state
@app.route('/api/agent/seating/state/<agent_id>', methods=['GET'])
def get_agent_seating_state(agent_id):
    """Get current seating state for an agent"""
    state = _seating_manager.get_agent_state(agent_id)

    if not state:
        # Auto-register agent if not found
        state = _seating_manager.register_agent(agent_id, mode='auto_seat')

    return jsonify({'ok': True, 'state': state})

# Endpoint: POST /api/agent/seating/update - Update agent seating state
@app.route('/api/agent/seating/update', methods=['POST'])
def update_agent_seating_state():
    """
    Update agent seating state with new signals from browser.

    Payload:
    {
        "agent_id": "bot_1",
        "hero_seat_detected": true,
        "stack_visible": true,
        "action_buttons_visible": false,
        "buyin_modal_visible": false,
        "table_id": "table_123",
        "seat_index": 3,
        ...
    }
    """
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    agent_id = payload.get('agent_id')
    if not agent_id:
        return jsonify({'ok': False, 'error': 'Missing agent_id'}), 400

    # Extract updates
    updates = {k: v for k, v in payload.items() if k != 'agent_id'}

    # Update state
    state = _seating_manager.update_agent_state(agent_id, updates)

    return jsonify({'ok': True, 'state': state})

# Endpoint: GET /api/agent/seating/next-action/<agent_id> - Get next seating action
@app.route('/api/agent/seating/next-action/<agent_id>', methods=['GET'])
def get_next_seating_action(agent_id):
    """
    Get the next executable action the agent should take.

    This is the DECISION ENGINE - it computes actions based on current state and signals.
    """
    next_action = _seating_manager.compute_next_action(agent_id)

    if not next_action:
        return jsonify({'ok': False, 'error': 'Agent not found'}), 404

    return jsonify({'ok': True, 'next_action': next_action})

# Endpoint: POST /api/agent/seating/reset/<agent_id> - Reset agent to IDLE
@app.route('/api/agent/seating/reset/<agent_id>', methods=['POST'])
def reset_agent_seating(agent_id):
    """Reset agent seating state to IDLE"""
    _seating_manager.reset_agent(agent_id)
    state = _seating_manager.get_agent_state(agent_id)

    return jsonify({'ok': True, 'state': state})

# Endpoint: GET /api/agent/seating/all - Get all agents
@app.route('/api/agent/seating/all', methods=['GET'])
def get_all_agents_seating():
    """Get seating state for all agents"""
    agents = _seating_manager.get_all_agents()
    return jsonify({'ok': True, 'agents': agents, 'count': len(agents)})

# ============================================================================
# HAND COLLECTION API ENDPOINTS
# ============================================================================

# Endpoint: GET /api/hand/latest - Get latest hand data
@app.route('/api/hand/latest', methods=['GET'])
def get_latest_hand():
    """Get the latest parsed hand for copy/paste"""
    with _hand_lock:
        return jsonify({
            'ok': True,
            'hand_id': _current_hand['hand_id'],
            'status': _current_hand['status'],
            'street': _current_hand['street'],
            'raw_text': _current_hand['raw_text'],
            'updated_at': _current_hand['updated_at']
        })

# Endpoint: POST /api/hand/update - Update current hand data
@app.route('/api/hand/update', methods=['POST'])
def update_hand_data():
    """
    Update hand data from collector/scraper.

    Payload:
    {
        "hand_id": "tbl123_1743300012",
        "status": "complete",
        "street": "river",
        "raw_text": "formatted hand text here",
    }
    """
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    with _hand_lock:
        _current_hand['hand_id'] = payload.get('hand_id')
        _current_hand['status'] = payload.get('status', 'collecting')
        _current_hand['street'] = payload.get('street', 'waiting')
        _current_hand['raw_text'] = payload.get('raw_text', '')
        _current_hand['updated_at'] = datetime.utcnow().isoformat()

    return jsonify({'ok': True})

# Endpoint: POST /api/hand/clear - Clear current hand
@app.route('/api/hand/clear', methods=['POST'])
def clear_hand_data():
    """Clear current hand data"""
    with _hand_lock:
        _current_hand['hand_id'] = None
        _current_hand['status'] = 'cleared'
        _current_hand['street'] = 'waiting'
        _current_hand['raw_text'] = ''
        _current_hand['updated_at'] = datetime.utcnow().isoformat()

    return jsonify({'ok': True})

# Endpoint: POST /api/hands/hole-card - Process hole card detection
@app.route('/api/hands/hole-card', methods=['POST'])
def process_hole_card():
    """
    Process hole card detection from n4p.js

    Payload:
    {
        "card": "As",
        "timestamp": 1712345678.12
    }
    """
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    card = payload.get('card')
    ts = payload.get('timestamp', time.time())

    if not card:
        return jsonify({'ok': False, 'error': 'Missing card'}), 400

    with _hand_lock:
        on_hole_card(card, ts)

    return jsonify({'ok': True})

# Endpoint: POST /api/hands/board - Process board cards detection
@app.route('/api/hands/board', methods=['POST'])
def process_board_cards():
    """
    Process board card detection from n4p.js

    Payload:
    {
        "board": ["Kh", "7d", "2s"],  // flop
        "board": ["Kh", "7d", "2s", "Jc"],  // turn
        "board": ["Kh", "7d", "2s", "Jc", "5h"]  // river
    }
    """
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    board = payload.get('board', [])

    if not board:
        return jsonify({'ok': False, 'error': 'Missing board'}), 400

    with _hand_lock:
        on_board_cards(board)

    return jsonify({'ok': True})

# Endpoint: GET /api/hands/recent - Get recent hand history
@app.route('/api/hands/recent', methods=['GET'])
def get_recent_hands():
    """
    Get recent hand history (last N hands)

    Query params:
    - limit: max number of hands to return (default 20, max 50)

    Returns:
    {
        "ok": true,
        "hands": ["hand1_text", "hand2_text", ...],
        "count": 20
    }
    """
    limit = min(int(request.args.get('limit', 20)), 50)

    with _hand_lock:
        recent_hands = _hand_history[-limit:] if len(_hand_history) > limit else _hand_history

    return jsonify({
        'ok': True,
        'hands': recent_hands,
        'count': len(recent_hands)
    })

# Endpoint: POST /api/hands/clear-history - Clear hand history
@app.route('/api/hands/clear-history', methods=['POST'])
def clear_hand_history():
    """Clear all hand history"""
    global _hand_history, _active_hand

    with _hand_lock:
        _hand_history = []
        _active_hand = None

    return jsonify({'ok': True})

# ============================================================================
# EQUITY ANALYSIS API ENDPOINTS
# ============================================================================

# Endpoint: POST /api/equity/analyze - Run equity analysis
@app.route('/api/equity/analyze', methods=['POST'])
def analyze_equity():
    """
    Analyze PLO4 equity for all pairs given textarea input.

    Expected payload format:
    {
        "hands_input": "4c2hTsKs\\n9s8dThTc\\nQd2c5sJd\\n...\\n\\n9h8h7c",
        "variant": "plo4-9max"  // optional, defaults to plo4-9max
    }

    Supported variants:
    - plo4-6max, plo4-9max (4 cards per hand)
    - plo5-6max, plo5-hu (5 cards per hand)
    - plo6-6max (6 cards per hand)
    - plo7-6max (7 cards per hand)

    Returns:
    {
        "ok": true,
        "status": "Done",
        "variant": "plo4-9max",
        "street": "FLOP",
        "pair_count": 36,
        "cpu_cores": 2,
        "runtime_seconds": 2.37,
        "rows": [...],
        "best_buy": {...},
        "worst_buy": {...}
    }
    """
    start_time = time.time()

    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    hands_input = payload.get('hands_input', '').strip()
    if not hands_input:
        return jsonify({'ok': False, 'error': 'Missing hands_input'}), 400

    # Variant selection with validation
    variant = payload.get('variant', 'plo4-9max').strip().lower()

    VARIANT_CONFIG = {
        'plo4-6max': {'cards': 4, 'players': 6, 'script': 'plo4-6max.py'},
        'plo4-8max': {'cards': 4, 'players': 8, 'script': 'plo4-8max.py'},
        'plo4-9max': {'cards': 4, 'players': 9, 'script': 'plo4-9max.py'},
        'plo5-5max': {'cards': 5, 'players': 5, 'script': 'plo5-5max.py'},
        'plo5-6max': {'cards': 5, 'players': 6, 'script': 'plo5-6max.py'},
        'plo5-8max': {'cards': 5, 'players': 8, 'script': 'plo5-8max.py'},
        'plo5-9max': {'cards': 5, 'players': 9, 'script': 'plo5-9max.py'},
        'plo5-hu':   {'cards': 5, 'players': 5, 'script': 'plo5-5max.py'},
        'plo6-5max': {'cards': 6, 'players': 5, 'script': 'plo6-5max.py'},
        'plo6-6max': {'cards': 6, 'players': 6, 'script': 'plo6-6max.py'},
        'plo6-8max': {'cards': 6, 'players': 8, 'script': 'plo6-8max.py'},
        'plo7-5max': {'cards': 7, 'players': 5, 'script': 'plo7-5max.py'},
        'plo7-6max': {'cards': 7, 'players': 7, 'script': 'plo7-6max.py'},
    }

    if variant not in VARIANT_CONFIG:
        return jsonify({'ok': False, 'error': f'Unknown variant: {variant}. Supported: {", ".join(sorted(VARIANT_CONFIG.keys()))}'}), 400

    vconf = VARIANT_CONFIG[variant]
    required_cards = vconf['cards']
    max_players = vconf['players']

    # Sanitize: strip ALL whitespace from the entire input (mandatory per acceptance criteria)
    # Then re-split on newlines only
    sanitized_lines = []
    for raw_line in hands_input.split('\n'):
        cleaned = re.sub(r'\s+', '', raw_line)
        sanitized_lines.append(cleaned)

    # Parse input: hands before blank line, board after blank line
    hand_lines = []
    board_line = None
    blank_found = False

    for cleaned in sanitized_lines:
        if not cleaned:
            blank_found = True
            continue
        if not blank_found:
            if len(cleaned) >= 4:
                hand_lines.append(cleaned)
        else:
            if not board_line:
                board_line = cleaned

    # Validate hand card counts
    valid_suits = {'h', 'd', 'c', 's'}
    valid_ranks = {'2','3','4','5','6','7','8','9','T','J','Q','K','A'}
    all_cards_seen = set()

    for idx, hand in enumerate(hand_lines):
        if len(hand) % 2 != 0:
            return jsonify({'ok': False, 'error': f'Hand {idx+1}: odd character count "{hand}" ({len(hand)} chars)'}), 400
        card_count = len(hand) // 2
        if card_count != required_cards:
            return jsonify({'ok': False, 'error': f'Hand {idx+1}: "{hand}" has {card_count} cards, {variant} requires {required_cards}'}), 400
        # Validate individual cards and check duplicates
        for ci in range(0, len(hand), 2):
            rank = hand[ci].upper()
            suit = hand[ci+1].lower()
            card_str = rank + suit
            if rank not in valid_ranks:
                return jsonify({'ok': False, 'error': f'Hand {idx+1}: invalid rank "{hand[ci]}" in "{hand}"'}), 400
            if suit not in valid_suits:
                return jsonify({'ok': False, 'error': f'Hand {idx+1}: invalid suit "{hand[ci+1]}" in "{hand}"'}), 400
            if card_str in all_cards_seen:
                return jsonify({'ok': False, 'error': f'Duplicate card: {card_str}'}), 400
            all_cards_seen.add(card_str)

    # Validate board cards if present
    if board_line:
        if len(board_line) % 2 != 0:
            return jsonify({'ok': False, 'error': f'Board: odd character count "{board_line}"'}), 400
        board_card_count = len(board_line) // 2
        if board_card_count != 3:
            return jsonify({'ok': False, 'error': f'Board must be 3 cards (flop only), got {board_card_count}'}), 400
        for ci in range(0, len(board_line), 2):
            rank = board_line[ci].upper()
            suit = board_line[ci+1].lower()
            card_str = rank + suit
            if rank not in valid_ranks:
                return jsonify({'ok': False, 'error': f'Board: invalid rank "{board_line[ci]}"'}), 400
            if suit not in valid_suits:
                return jsonify({'ok': False, 'error': f'Board: invalid suit "{board_line[ci+1]}"'}), 400
            if card_str in all_cards_seen:
                return jsonify({'ok': False, 'error': f'Duplicate card on board: {card_str}'}), 400
            all_cards_seen.add(card_str)

    if len(hand_lines) < 2:
        return jsonify({'ok': False, 'error': f'Need at least 2 hands (got {len(hand_lines)})'}), 400

    # Generate dummy cards for padding (cards not already in use)
    def generate_dummy_hand(used_cards, num_cards):
        all_ranks = ['2','3','4','5','6','7','8','9','T','J','Q','K','A']
        all_suits_list = ['s','h','d','c']
        dummy = []
        for r in all_ranks:
            for s in all_suits_list:
                cs = r + s
                if cs not in used_cards:
                    dummy.append(cs)
                    used_cards.add(cs)
                    if len(dummy) == num_cards:
                        return ''.join(dummy)
        return ''.join(dummy)

    # Pad to required player count
    while len(hand_lines) < max_players:
        hand_lines.append(generate_dummy_hand(all_cards_seen, required_cards))

    # Truncate to max players
    hand_lines = hand_lines[:max_players]

    # Resolve script path and Python executable
    script_dir = '/opt/plo-test/engine/scripts'
    script_path = os.path.join(script_dir, vconf['script'])
    if not os.path.exists(script_path):
        return jsonify({'ok': False, 'error': f'Engine script not found for variant {variant}'}), 500

    python_venv = '/home/warrenabrahams/2_DEVELOPMENT/environments/plo_sim/bin/python'

    # Create temp file for engine script
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmpf:
            temp_path = tmpf.name

            for hand in hand_lines:
                tmpf.write(f"{hand}\n")

            if board_line:
                tmpf.write(f"{board_line}\n")

        if not os.path.exists(python_venv):
            python_venv = sys.executable

        result = subprocess.run(
            [python_venv, script_path, temp_path],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd='/home/warrenabrahams'
        )

        # Parse output
        output = result.stdout

        # Determine street (FLOP only per acceptance criteria)
        street = "PREFLOP"
        if board_line:
            board_len = len(board_line) // 2
            if board_len == 3:
                street = "FLOP"

        # Calculate pair count from actual player count
        actual_players = min(len(hand_lines), max_players)
        pair_count = actual_players * (actual_players - 1) // 2

        # Parse the ranked results from output
        # Look for the "ALL MATCHUPS" section
        rows = []

        # Regex to extract ranked matchups table
        # Format: Rank  #  Underdog  Favourite  UndRaw  UndReal  Disparity  FavRaw  FavReal
        # Example: "     1   12  Kd4s7h8h (Player6)        As9s8d7d (Player2)        43.7195%  36.5385%   -7.1811%  56.2805%  63.4615% ★"
        # Note: Positive disparities have extra spaces: "+  0.0063%" so we need to handle that
        pattern = r'^\s*(\d+)\s+(\d+)\s+([A-Za-z0-9]+)\s+\(([^)]+)\)\s+([A-Za-z0-9]+)\s+\(([^)]+)\)\s+([\d.]+)%\s+([\d.]+)%\s+([+\-])?\s*(\d+\.\d+)%\s+([\d.]+)%\s+([\d.]+)%'

        for line in output.split('\n'):
            match = re.search(pattern, line)
            if match:
                rank = int(match.group(1))
                pair_no = int(match.group(2))
                underdog_hand = match.group(3)
                underdog_player = match.group(4)
                fav_hand = match.group(5)
                fav_player = match.group(6)
                und_raw = float(match.group(7))
                und_real = float(match.group(8))
                sign = match.group(9) or ''  # '+' or '-' or None
                disparity_val = float(match.group(10))
                disparity = disparity_val if sign != '-' else -disparity_val
                fav_raw = float(match.group(11))
                fav_real = float(match.group(12))

                # Parse hand into 4 cards
                buy_hand = parse_hand_to_cards(underdog_hand)
                reverse_hand = parse_hand_to_cards(fav_hand)

                row = {
                    'rank': rank,
                    'pair_no': pair_no,
                    'buy_hand': buy_hand,
                    'buy_player': underdog_player,
                    'reverse_hand': reverse_hand,
                    'reverse_player': fav_player,
                    'price': round(und_raw, 4),
                    'rev_buy_hit': round(und_real, 4),
                    'disparity': round(disparity, 4),
                    'rev_price': round(fav_raw, 4),
                    'hitrate': round(fav_real, 4)
                }
                rows.append(row)

        # Get best and worst
        best_buy = rows[0] if rows else None
        worst_buy = rows[-1] if rows else None

        runtime = time.time() - start_time

        response = {
            'ok': True,
            'status': 'Done',
            'variant': variant,
            'street': street,
            'pair_count': pair_count,
            'cpu_cores': cpu_count(),
            'runtime_seconds': round(runtime, 2),
            'rows': rows,
            'best_buy': best_buy,
            'worst_buy': worst_buy
        }

        return jsonify(response)

    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'error': 'Calculation timeout (>5 min)'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        # Clean up temp file
        if 'temp_path' in locals():
            try:
                os.unlink(temp_path)
            except:
                pass

def parse_hand_to_cards(hand_str):
    """Parse hand string like 'AhKhQdJd' into list of cards ['Ah','Kh','Qd','Jd']"""
    cards = []
    i = 0
    while i < len(hand_str):
        if i + 1 < len(hand_str):
            if hand_str[i:i+2] == '10':
                rank = 'T'
                suit = hand_str[i+2] if i+2 < len(hand_str) else ''
                i += 3
            else:
                rank = hand_str[i]
                suit = hand_str[i+1]
                i += 2

            if suit:
                cards.append(f"{rank}{suit}")

    return cards


# ============================================================================
# POKER CLOCK API ENDPOINTS
# ============================================================================

# Endpoint: GET /api/clock/state - Get current clock state
@app.route('/api/clock/state', methods=['GET'])
def get_clock_state():
    """Get current tournament clock state"""
    clock = get_clock()
    state = clock.get_state()
    return jsonify({'ok': True, 'state': state})


# Endpoint: POST /api/clock/start - Start/resume clock
@app.route('/api/clock/start', methods=['POST'])
def start_clock():
    """Start or resume tournament clock"""
    clock = get_clock()
    result = clock.start()
    return jsonify({'ok': result.get('success', False), **result})


# Endpoint: POST /api/clock/pause - Pause clock
@app.route('/api/clock/pause', methods=['POST'])
def pause_clock():
    """Pause tournament clock"""
    clock = get_clock()
    result = clock.pause()
    return jsonify({'ok': result.get('success', False), **result})


# Endpoint: POST /api/clock/reset - Reset clock to level 1
@app.route('/api/clock/reset', methods=['POST'])
def reset_clock():
    """Reset clock to level 1"""
    clock = get_clock()
    result = clock.reset()
    return jsonify({'ok': result.get('success', False), **result})


# Endpoint: POST /api/clock/advance - Advance to next level
@app.route('/api/clock/advance', methods=['POST'])
def advance_clock():
    """Manually advance to next blind level"""
    clock = get_clock()
    result = clock.advance_level()
    return jsonify({'ok': result.get('success', False), **result})


# Endpoint: POST /api/clock/add-time - Add/subtract time
@app.route('/api/clock/add-time', methods=['POST'])
def add_clock_time():
    """
    Add or subtract time from current level

    Payload:
    {
        "minutes": 5  // positive to add, negative to subtract
    }
    """
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    minutes = payload.get('minutes', 0)
    if not isinstance(minutes, (int, float)):
        return jsonify({'ok': False, 'error': 'Invalid minutes value'}), 400

    clock = get_clock()
    result = clock.add_time(int(minutes))
    return jsonify({'ok': result.get('success', False), **result})


# Endpoint: POST /api/clock/structure - Update blind structure
@app.route('/api/clock/structure', methods=['POST'])
def update_clock_structure():
    """
    Update tournament blind structure

    Payload:
    {
        "structure": [
            {
                "level": 1,
                "small_blind": 25,
                "big_blind": 50,
                "ante": 0,
                "duration_minutes": 20,
                "is_break": false
            },
            ...
        ]
    }
    """
    payload = request.get_json()
    if not payload:
        return jsonify({'ok': False, 'error': 'No payload'}), 400

    structure = payload.get('structure', [])
    if not isinstance(structure, list):
        return jsonify({'ok': False, 'error': 'Invalid structure format'}), 400

    clock = get_clock()
    result = clock.update_structure(structure)
    return jsonify({'ok': result.get('success', False), **result})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
