"""Equity blueprint — in-process eval7 engine. Replaces the legacy er-engine :5002 hop."""

from __future__ import annotations

import time

from flask import Blueprint, jsonify, request

from webapp import equity

equity_bp = Blueprint("equity", __name__)


@equity_bp.post("/api/equity")
def api_equity():
    try:
        import eval7  # noqa: F401 — probe availability
    except ImportError:
        return jsonify({"ok": False, "error": "eval7 not installed"}), 503

    data = request.get_json(silent=True) or {}
    variant = data.get("variant", "nlhe")
    hands = data.get("hands")
    board = data.get("board") or []
    samples = data.get("samples")
    if not isinstance(hands, list) or len(hands) < 2:
        return jsonify({"ok": False, "error": "hands must be a list of >= 2 hands"}), 400
    try:
        result = equity.equity(hands, board, variant, samples=samples)
    except equity.EquityError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, **result, "backend": "eval7"})


@equity_bp.get("/api/engine/status")
def engine_status():
    try:
        import eval7
        ok, ver = True, getattr(eval7, "__version__", "0.1.10")
    except ImportError:
        ok, ver = False, None
    return jsonify({
        "service": "equity-engine",
        "status": "healthy" if ok else "offline",
        "mode": "in-process",
        "backend": "eval7",
        "version": ver,
        "engine_url": None,
        "timestamp": time.time(),
    })
