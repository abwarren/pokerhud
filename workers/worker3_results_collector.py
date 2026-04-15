#!/usr/bin/env python3
"""
Worker 3: Results Collector
============================
Collects finished tournament results - final standings, payouts, player performance.
Polls every 2 minutes for completed tournaments.
"""

import json
import time
import logging
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor
import requests

# Database config
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'pokerhud',
    'user': 'warrenabrahams',
    'password': 'pokerhud'
}

# PokerBet API endpoints
PARTNER_ID = '18751019'
HANDS_BASE = 'https://poker-hands.skillgames-bc.com'

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [RESULTS] %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/opt/pokerhud/logs/worker3_results.log')
    ]
)
log = logging.getLogger('results_collector')

BROWSER_HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
    'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/146.0'
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def get_running_tournaments():
    """Get tournaments that might have finished."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, name, external_id, status, players_registered,
               prize_pool_guaranteed_zar, prize_pool_actual_zar, buy_in_total_zar
        FROM tournaments
        WHERE status IN ('running', 'late_reg')
        AND scraped_at > NOW() - INTERVAL '12 hours'
        ORDER BY scraped_at DESC
    """)
    tournaments = cur.fetchall()
    cur.close()
    conn.close()
    return tournaments


def get_recently_finished():
    """Get tournaments marked as finished in last 24 hours without results."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT t.id, t.name, t.external_id, t.prize_pool_actual_zar,
               t.players_registered, t.buy_in_total_zar
        FROM tournaments t
        LEFT JOIN tournament_results tr ON t.id = tr.tournament_id
        WHERE t.status = 'finished'
        AND t.scraped_at > NOW() - INTERVAL '24 hours'
        AND tr.id IS NULL
        ORDER BY t.scraped_at DESC
    """)
    tournaments = cur.fetchall()
    cur.close()
    conn.close()
    return tournaments


def check_if_tournament_finished(tournament):
    """Check various signals to determine if tournament is finished."""
    # For now, check if tournament has been running for expected duration
    # Real implementation would poll the WebSocket for status updates
    external_id = tournament.get('external_id')
    if not external_id:
        return False

    # Try to fetch hand history (finished tournaments have complete history)
    try:
        url = f'{HANDS_BASE}/api/hands'
        params = {
            'partnerId': PARTNER_ID,
            'tournamentId': external_id,
            'limit': 1
        }
        resp = requests.get(url, params=params, headers=BROWSER_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # If we get hands and tournament data indicates completion
            if data and isinstance(data, list) and len(data) > 0:
                # Check for tournament end markers in hand data
                for hand in data:
                    if hand.get('tournamentFinished') or hand.get('is_final_hand'):
                        return True
    except Exception as e:
        log.debug(f'Hand history check failed: {e}')

    return False


def fetch_tournament_results(tournament):
    """Fetch final results for a tournament."""
    external_id = tournament.get('external_id')
    results = []

    # Try to get results from hand history endpoint
    try:
        url = f'{HANDS_BASE}/api/tournament/results'
        params = {
            'partnerId': PARTNER_ID,
            'tournamentId': external_id
        }
        resp = requests.get(url, params=params, headers=BROWSER_HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                for idx, player in enumerate(data):
                    result = {
                        'tournament_id': tournament['id'],
                        'player_name': player.get('name', player.get('playerName', f'Player{idx+1}')),
                        'site': 'pokerbet',
                        'finish_position': player.get('position', player.get('rank', idx + 1)),
                        'payout_zar': float(player.get('payout', player.get('prize', 0))),
                        'is_hero': player.get('isHero', False)
                    }
                    results.append(result)
    except Exception as e:
        log.debug(f'Results fetch failed: {e}')

    return results


def save_tournament_results(results):
    """Save results to tournament_results table."""
    if not results:
        return 0

    conn = get_db_connection()
    cur = conn.cursor()
    saved = 0

    for r in results:
        try:
            cur.execute('''
                INSERT INTO tournament_results (
                    tournament_id, player_name, site, finish_position,
                    payout_zar, is_hero, created_at
                ) VALUES (
                    %(tournament_id)s, %(player_name)s, %(site)s, %(finish_position)s,
                    %(payout_zar)s, %(is_hero)s, NOW()
                )
                ON CONFLICT (tournament_id, player_name)
                DO UPDATE SET
                    finish_position = EXCLUDED.finish_position,
                    payout_zar = EXCLUDED.payout_zar
            ''', r)
            saved += 1
        except Exception as e:
            log.error(f"Error saving result for {r.get('player_name')}: {e}")
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()
    return saved


def update_tournament_finished(tournament_id, actual_prize_pool=None):
    """Mark tournament as finished and update prize pool."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        if actual_prize_pool:
            cur.execute("""
                UPDATE tournaments
                SET status = 'finished', prize_pool_actual_zar = %s, scraped_at = NOW()
                WHERE id = %s
            """, (actual_prize_pool, tournament_id))
        else:
            cur.execute("""
                UPDATE tournaments
                SET status = 'finished', scraped_at = NOW()
                WHERE id = %s
            """, (tournament_id,))
        conn.commit()
    except Exception as e:
        log.error(f'Error updating tournament status: {e}')
        conn.rollback()

    cur.close()
    conn.close()


def calculate_prize_pool(tournament, results):
    """Calculate actual prize pool from results."""
    if results:
        total = sum(r.get('payout_zar', 0) for r in results)
        if total > 0:
            return total

    # Fallback: use guarantee or calculate from entries
    if tournament.get('prize_pool_guaranteed_zar'):
        players = tournament.get('players_registered', 0)
        buyin = tournament.get('buy_in_total_zar', 0)
        if players and buyin:
            # Prize pool = max(guarantee, entries * buyin * 0.9)  # 10% rake
            calculated = players * buyin * 0.9
            return max(tournament['prize_pool_guaranteed_zar'], calculated)
        return tournament['prize_pool_guaranteed_zar']

    return None


def run_once():
    """Run a single results collection cycle."""
    log.info('Starting results collection cycle...')

    # Check running tournaments to see if any finished
    running = get_running_tournaments()
    finished_count = 0

    for t in running:
        if check_if_tournament_finished(t):
            log.info(f"Tournament finished: {t['name']}")

            # Fetch and save results
            results = fetch_tournament_results(t)
            if results:
                saved = save_tournament_results(results)
                log.info(f"Saved {saved} results for {t['name']}")

            # Calculate prize pool and mark finished
            prize_pool = calculate_prize_pool(t, results)
            update_tournament_finished(t['id'], prize_pool)
            finished_count += 1

    # Also check recently finished tournaments without results
    no_results = get_recently_finished()
    for t in no_results:
        results = fetch_tournament_results(t)
        if results:
            saved = save_tournament_results(results)
            log.info(f"Saved {saved} results for finished tournament {t['name']}")

    log.info(f'Cycle complete: {finished_count} tournaments finished, checked {len(running)} running')
    return finished_count


def main():
    """Main loop - collect every 2 minutes."""
    log.info('Worker 3 (Results Collector) starting...')

    while True:
        try:
            run_once()
        except Exception as e:
            log.error(f'Main loop error: {e}')

        log.info('Sleeping 2 minutes...')
        time.sleep(120)


if __name__ == '__main__':
    main()
