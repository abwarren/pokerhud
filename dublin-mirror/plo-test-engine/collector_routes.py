"""
Hand Collector Routes for PLO Remote Control
Collects hole cards and board from players for equity analysis
"""

import re
import threading
from collections import OrderedDict
from flask import jsonify, request, send_from_directory

# Global state
collector_hands = OrderedDict()
collector_board = ""
collector_lock = threading.Lock()

# Card normalization regex
CARD_RE = re.compile(r'^(10|[2-9AKQJTakqjt])([hdcsHDCS])$')


def normalize(card):
    """Normalize card format to Ts, Ah, 9c, etc."""
    m = CARD_RE.match(str(card).strip())
    if not m:
        return None

    rank, suit = m.groups()
    rank = rank.upper()
    if rank == "10":
        rank = "T"

    return f"{rank}{suit.lower()}"


def normalize_cards(cards):
    """Normalize a list of cards"""
    out = []
    if not isinstance(cards, list):
        return out

    for c in cards:
        n = normalize(c)
        if n:
            out.append(n)

    return out


def register_collector_routes(app):
    """Register collector routes with Flask app - ALL use /api/collector/* prefix"""

    @app.route("/api/collector/status")
    def collector_status():
        """Collector status/health check"""
        with collector_lock:
            return jsonify({
                "ok": True,
                "status": "active",
                "hands": len(collector_hands),
                "board": collector_board
            })

    @app.route("/api/collector/player-state", methods=["POST"])
    def collector_player_state():
        """Receive player hole cards and board"""
        global collector_board

        data = request.get_json(force=True, silent=True) or {}
        cards = normalize_cards(data.get("cards", []))
        brd = normalize_cards(data.get("board", []))

        with collector_lock:
            if cards:
                hand = "".join(cards)
                collector_hands[hand] = True

            if brd:
                collector_board = "".join(brd)

        return jsonify({"ok": True})

    @app.route("/api/collector/hands")
    def collector_hands_api():
        """Return all collected hands as JSON"""
        with collector_lock:
            hands_list = list(collector_hands.keys())
            return jsonify({
                "ok": True,
                "hands": hands_list,
                "board": collector_board,
                "total": len(hands_list)
            })

    @app.route("/api/collector/ascii")
    def collector_ascii_all():
        """Return all collected hands as plain text (legacy)"""
        with collector_lock:
            lines = list(collector_hands.keys())
            if collector_board:
                lines.append(collector_board)

        return "\n".join(lines), 200, {'Content-Type': 'text/plain'}

    @app.route("/api/collector/latest")
    def collector_latest():
        """Return latest collected hands as raw text (for engine auto-fill)"""
        with collector_lock:
            lines = list(collector_hands.keys())
            if collector_board:
                lines.append(collector_board)

        raw = "\n".join(lines) if lines else ""
        return jsonify({"ok": True, "raw": raw})

    @app.route("/api/collector/clear", methods=["POST"])
    def collector_clear():
        """Clear all collected hands and board"""
        global collector_board
        with collector_lock:
            collector_hands.clear()
            collector_board = ""
        return jsonify({"ok": True})
