#!/usr/bin/env python3
"""
Snapshot Receiver — port 8888
Receives POST /api/snapshot from Chrome extension background.js
Logs to console + saves to JSON for debugging
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import json
import os

app = Flask(__name__)
CORS(app)

SNAPSHOT_DIR = "/opt/pokerhud/snapshots"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

snapshot_count = 0


@app.route("/api/snapshot", methods=["POST"])
def receive_snapshot():
    global snapshot_count
    snapshot_count += 1
    data = request.get_json(silent=True) or {}

    # Extract key fields
    table = data.get("table", {})
    hero = data.get("hero") or {}
    players = data.get("players", [])
    board = data.get("board", {})

    print(f"\n{'='*50}")
    print(f"=== SNAPSHOT RECEIVED #{snapshot_count} ===")
    print(f"{'='*50}")
    print(f"  URL:     {data.get('url', '?')}")
    print(f"  Time:    {datetime.now().strftime('%H:%M:%S')}")
    print(f"  Players: {table.get('playerCount', '?')} at table")
    print(f"  Dealer:  seat {table.get('dealerPosition', '?')}")
    print(f"  Pot:     {table.get('potText', '?')}")
    print(f"  Hero:    {hero.get('name', 'NOT FOUND')} — stack: {hero.get('stack', '?')}")
    print(f"  Board:   {[c.get('text','?') for c in board.get('cards', [])]}")
    print(f"  Seats:")
    for p in players:
        marker = " ★" if p.get("isHero") else ""
        sit = " [SITTING OUT]" if p.get("isSittingOut") else ""
        cards = [c.get("text", "?") for c in p.get("cards", [])]
        print(f"    seat {p.get('position','?'):>2}: {p.get('name','?'):20s} stack={p.get('stack','?'):>10s} cards={cards}{marker}{sit}")

    # Save latest snapshot
    with open(os.path.join(SNAPSHOT_DIR, "latest.json"), "w") as f:
        json.dump(data, f, indent=2)

    # Append to log
    with open(os.path.join(SNAPSHOT_DIR, "snapshot_log.jsonl"), "a") as f:
        f.write(json.dumps({"n": snapshot_count, "ts": datetime.now().isoformat(), **data}) + "\n")

    return jsonify({"ok": True, "n": snapshot_count})


@app.route("/api/snapshot/latest", methods=["GET"])
def get_latest():
    path = os.path.join(SNAPSHOT_DIR, "latest.json")
    if os.path.exists(path):
        with open(path) as f:
            return jsonify(json.load(f))
    return jsonify({"error": "no snapshots yet"}), 404


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "snapshots": snapshot_count})


if __name__ == "__main__":
    print("=" * 50)
    print("SNAPSHOT RECEIVER — port 8888")
    print("Waiting for Chrome extension snapshots...")
    print("=" * 50)
    app.run(host="0.0.0.0", port=8888, debug=True)
