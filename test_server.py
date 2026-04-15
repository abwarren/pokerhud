#!/usr/bin/env python3
"""
Simple Flask server to receive PokerBet snapshots from Chrome extension
Runs on localhost:8888
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)

@app.route('/api/snapshot', methods=['POST'])
def receive_snapshot():
    """Receive snapshot from Chrome extension"""
    data = request.get_json()

    print("\n" + "="*60)
    print("=== SNAPSHOT RECEIVED ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*60)

    if data:
        print(f"\nSite: {data.get('site', 'unknown')}")
        print(f"URL: {data.get('url', 'unknown')}")

        # Table info
        table = data.get('table', {})
        print(f"\nTable:")
        print(f"  Player Count: {table.get('playerCount', 'N/A')}")
        print(f"  Dealer Position: {table.get('dealerPosition', 'N/A')}")
        print(f"  Pot: {table.get('potText', 'N/A')}")

        # Hero info
        hero = data.get('hero')
        if hero:
            print(f"\nHero:")
            print(f"  Name: {hero.get('name', 'N/A')}")
            print(f"  Stack: {hero.get('stack', 'N/A')}")
            print(f"  Position: {hero.get('position', 'N/A')}")

        # Players
        players = data.get('players', [])
        print(f"\nPlayers: {len(players)}")
        for p in players[:3]:  # Show first 3
            print(f"  - Pos {p.get('position')}: {p.get('name')} ({p.get('stack')})")

        # Board
        board = data.get('board', {})
        cards = board.get('cards', [])
        print(f"\nBoard Cards: {len(cards)}")
        if cards:
            for card in cards[:5]:  # Show first 5
                print(f"  - {card.get('text', 'N/A')}")

        # Raw JSON for debugging
        print(f"\n--- RAW JSON (first 500 chars) ---")
        json_str = json.dumps(data, indent=2)
        print(json_str[:500])
        if len(json_str) > 500:
            print(f"... ({len(json_str)} total chars)")

        print("\n" + "="*60 + "\n")

        return jsonify({"status": "received", "timestamp": datetime.now().isoformat()}), 200
    else:
        print("ERROR: No data received")
        return jsonify({"error": "No data"}), 400

@app.route('/api/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({"status": "ok", "server": "pokerhud-test", "port": 8888}), 200

if __name__ == '__main__':
    print("="*60)
    print("PokerBet HUD Test Server")
    print("="*60)
    print("Listening on: http://127.0.0.1:8888")
    print("Endpoint: POST /api/snapshot")
    print("Health: GET /api/health")
    print("\nWaiting for snapshots from Chrome extension...")
    print("="*60 + "\n")

    app.run(host='127.0.0.1', port=8888, debug=True)
