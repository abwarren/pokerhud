#!/usr/bin/env python3
"""
Cyber Basketball 2K26 Results Scraper
Hits BetConstruct's swarm/feed endpoints to pull historical game results.
"""
import json
import time
import sys
import sqlite3
import os
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# BetConstruct partner IDs found in PokerBet's frontend
PARTNER_ID = 1775  # PokerBet's BC partner ID — may need adjustment

# Known BetConstruct API patterns for virtual sports results
ENDPOINTS = [
    # Swarm REST fallback
    "https://eu-swarm-spring-cloud.betconstruct.com/",
    "https://swarm-spring-cloud.betconstruct.com/",
    # Virtual sports results feeds
    "https://cms2.betconstruct.com/",
    # PokerBet specific
    "https://www.pokerbet.co.za/",
]

BLM_DB = '/opt/plo-w4p/blm.db'

def fetch_json(url, data=None, headers=None, timeout=10):
    """Simple HTTP fetch returning parsed JSON."""
    if headers is None:
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
    if data and isinstance(data, dict):
        data = json.dumps(data).encode('utf-8')
    req = Request(url, data=data, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except (URLError, HTTPError) as e:
        return {'error': str(e)}
    except Exception as e:
        return {'error': str(e)}


def try_swarm_request(base_url, command, params=None):
    """Send a swarm-style request."""
    payload = {
        "command": command,
        "params": params or {},
    }
    result = fetch_json(base_url, data=payload)
    return result


def try_betconstruct_results():
    """Try various BetConstruct endpoints for virtual basketball results."""
    results = {}

    # Method 1: Swarm get_result command
    for base in ENDPOINTS[:2]:
        print(f"\n[TRY] Swarm results via {base}")
        r = try_swarm_request(base, "get", {
            "source": "betting",
            "what": {
                "sport": {"@id": True},
                "region": {},
                "competition": {},
                "game": {
                    "@id": True,
                    "type": True,
                    "sport_id": True,
                    "scores": True,
                    "info": True,
                }
            },
            "where": {
                "sport": {"alias": "CyberBasketball2K26"},
                "game": {"type": {"@in": [0, 2]}}  # 0=prematch, 2=finished
            }
        })
        results['swarm_results'] = r
        if 'error' not in r:
            print(f"  [OK] Got data: {json.dumps(r)[:200]}")
            return r
        else:
            print(f"  [FAIL] {r['error'][:100]}")

    # Method 2: CMS results endpoint
    print("\n[TRY] CMS virtual results")
    for path in [
        "/api/virtual/results",
        "/api/results/cyber-basketball",
        "/JsonData/GetResults",
        "/api/sport/results",
    ]:
        for base in ENDPOINTS:
            url = base.rstrip('/') + path
            print(f"  Trying: {url}")
            r = fetch_json(url)
            if 'error' not in r:
                print(f"  [OK] {json.dumps(r)[:200]}")
                results[f'cms_{path}'] = r
                return r
            else:
                print(f"  [FAIL] {str(r.get('error',''))[:80]}")

    # Method 3: Direct REST API patterns used by BetConstruct partners
    print("\n[TRY] Partner REST API")
    rest_urls = [
        f"https://www.pokerbet.co.za/api/virtual/results?sport=basketball&count=100",
        f"https://www.pokerbet.co.za/api/sport/games?type=2&sport=cyber-basketball",
        f"https://virtual.betconstruct.com/api/v1/results?sport=basketball",
    ]
    for url in rest_urls:
        print(f"  Trying: {url}")
        r = fetch_json(url)
        if 'error' not in r:
            print(f"  [OK] {json.dumps(r)[:200]}")
            return r
        else:
            print(f"  [FAIL] {str(r.get('error',''))[:80]}")

    return results


def try_websocket_swarm():
    """
    Try the BetConstruct Swarm WebSocket protocol.
    The frontend uses WSS to swarm servers. We can try HTTP fallback.
    """
    print("\n[TRY] Swarm HTTP long-polling fallback")

    # BetConstruct Swarm uses session-based HTTP as fallback
    # Step 1: Create session
    for swarm_host in [
        "https://eu-swarm-spring-cloud.betconstruct.com",
        "https://swarm-spring-cloud.betconstruct.com",
    ]:
        print(f"\n  Host: {swarm_host}")

        # Register session
        session_req = {
            "command": "request_session",
            "params": {
                "site_id": PARTNER_ID,
                "language": "eng",
            }
        }
        r = fetch_json(swarm_host + "/", data=session_req)
        print(f"  Session: {json.dumps(r)[:200]}")

        if r.get('data', {}).get('sid'):
            sid = r['data']['sid']
            print(f"  [OK] Got session: {sid}")

            # Now request virtual basketball results
            games_req = {
                "command": "get",
                "params": {
                    "source": "betting",
                    "what": {
                        "game": ["id", "team1_name", "team2_name", "scores",
                                 "info", "start_ts", "game_number", "type",
                                 "markets_count"]
                    },
                    "where": {
                        "sport": {"alias": "CyberBasketball2K26"},
                        "game": {
                            "type": 2  # finished games
                        }
                    },
                    "subscribe": False
                },
                "rid": "results_1"
            }
            r2 = fetch_json(swarm_host + "/?sid=" + sid, data=games_req)
            print(f"  Results: {json.dumps(r2)[:500]}")

            if r2.get('data'):
                return r2

            # Try alternative sport aliases
            for alias in ['CyberBasketball', 'VirtualBasketball', 'Basketball2K26',
                          'Cyber Basketball 2K26 Matches', 'cyber_basketball_2k26']:
                alt_req = dict(games_req)
                alt_req['params']['where']['sport']['alias'] = alias
                alt_req['rid'] = f'results_{alias}'
                r3 = fetch_json(swarm_host + "/?sid=" + sid, data=alt_req)
                if r3.get('data', {}).get('data'):
                    print(f"  [OK] Found with alias: {alias}")
                    print(f"  Data: {json.dumps(r3)[:500]}")
                    return r3
                else:
                    print(f"  [{alias}] No data")

            # Try by sport ID instead of alias
            for sport_id in [195, 196, 197, 198, 199, 200, 250, 300]:
                id_req = {
                    "command": "get",
                    "params": {
                        "source": "betting",
                        "what": {
                            "sport": ["id", "alias", "name"],
                            "competition": ["id", "name"],
                            "game": ["id", "team1_name", "team2_name", "type",
                                     "start_ts", "scores"]
                        },
                        "where": {
                            "sport": {"id": sport_id},
                        },
                        "subscribe": False
                    },
                    "rid": f"sport_{sport_id}"
                }
                r4 = fetch_json(swarm_host + "/?sid=" + sid, data=id_req)
                data = r4.get('data', {}).get('data', {})
                if data and data.get('sport'):
                    sports = data['sport']
                    for sid_key, sport_data in sports.items():
                        print(f"  [SPORT {sport_id}] {sport_data.get('name', sport_data.get('alias', '?'))}")
                        if 'cyber' in str(sport_data).lower() or 'basketball' in str(sport_data).lower():
                            print(f"  [FOUND] {json.dumps(sport_data)[:500]}")
                            return r4

            # List all sports to find the right ID
            list_req = {
                "command": "get",
                "params": {
                    "source": "betting",
                    "what": {
                        "sport": ["id", "alias", "name", "order"]
                    },
                    "where": {},
                    "subscribe": False
                },
                "rid": "list_sports"
            }
            r5 = fetch_json(swarm_host + "/?sid=" + sid, data=list_req)
            sports_data = r5.get('data', {}).get('data', {}).get('sport', {})
            if sports_data:
                print(f"\n  === ALL SPORTS ({len(sports_data)}) ===")
                for k, v in sorted(sports_data.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
                    name = v.get('name', v.get('alias', '?'))
                    alias = v.get('alias', '?')
                    print(f"    ID={k:>4}  alias={alias:<40} name={name}")
                return r5

    return None


def save_games_to_db(games_data):
    """Parse swarm response and save to BLM database."""
    if not os.path.exists(BLM_DB):
        print(f"DB not found: {BLM_DB}")
        return 0

    db = sqlite3.connect(BLM_DB)
    count = 0
    for gid, game in games_data.items():
        try:
            home = game.get('team1_name', '')
            away = game.get('team2_name', '')
            scores = game.get('scores', {})
            # Parse scores
            hs = int(scores.get('team1_score', 0) or 0)
            as_ = int(scores.get('team2_score', 0) or 0)
            total = hs + as_

            start_ts = game.get('start_ts', 0)
            game_date = datetime.utcfromtimestamp(start_ts).strftime('%Y-%m-%d') if start_ts else None

            db.execute("""
                INSERT OR REPLACE INTO games
                (game_id, home_team, away_team, home_score, away_score, total_score,
                 status, game_date, league)
                VALUES (?, ?, ?, ?, ?, ?, 'final', ?, 'Cyber Basketball 2K26')
            """, (str(gid), home, away, hs, as_, total, game_date))
            count += 1
        except Exception as e:
            print(f"  Error saving game {gid}: {e}")

    db.commit()
    db.close()
    return count


if __name__ == '__main__':
    print("=" * 60)
    print("CB2K Results Scraper — Cyber Basketball 2K26")
    print("=" * 60)

    # Try direct API methods first
    result = try_betconstruct_results()
    if result and 'error' not in str(result)[:100]:
        print("\n[SUCCESS] Got data from REST API")
        print(json.dumps(result, indent=2)[:2000])
    else:
        # Try WebSocket/Swarm approach
        result = try_websocket_swarm()
        if result:
            print("\n[SWARM] Response received")
            # Check if we got games data
            games = result.get('data', {}).get('data', {}).get('game', {})
            if games:
                print(f"Found {len(games)} games")
                saved = save_games_to_db(games)
                print(f"Saved {saved} games to database")
            else:
                print("Full response:")
                print(json.dumps(result, indent=2)[:3000])
        else:
            print("\n[FAIL] Could not find working API endpoint")
            print("Will need to scrape via browser automation or manual entry")
