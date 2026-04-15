#!/usr/bin/env python3
"""
Worker 2: Active Tournament Tracker
====================================
Tracks running tournaments - monitors player counts, blind levels, prize pools.
Polls every 60 seconds for active tournament updates.
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

# PokerBet WebSocket/API endpoints
PARTNER_ID = '18751019'
PRODUCT_ID = '3'  # poker
GATEWAY_BASE = 'https://sg-api.skillgames-bc.com'
PROMO_BASE = 'https://poker-promotions.skillgames-bc.com'

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [ACTIVE] %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/opt/pokerhud/logs/worker2_active.log')
    ]
)
log = logging.getLogger('active_tracker')

BROWSER_HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
    'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Linux"',
    'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/146.0'
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def get_active_tournaments():
    """Get tournaments with status='running' from database."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, name, external_id, players_registered, players_max,
               prize_pool_actual_zar, status
        FROM tournaments
        WHERE status = 'running' OR status = 'late_reg'
        ORDER BY scraped_at DESC
    """)
    tournaments = cur.fetchall()
    cur.close()
    conn.close()
    return tournaments


def get_scheduled_near_start():
    """Get tournaments scheduled to start soon (mark as running)."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # Find tournaments that should have started based on schedule
    cur.execute("""
        SELECT id, name, external_id, schedule_day, start_time, status
        FROM tournaments
        WHERE status = 'scheduled'
        AND scraped_at > NOW() - INTERVAL '24 hours'
    """)
    tournaments = cur.fetchall()
    cur.close()
    conn.close()
    return tournaments


def check_tournament_status_api(external_id):
    """Try to get tournament status from BetConstruct API."""
    # Note: This requires authentication in most cases
    # We'll try the public promotion bonuses endpoint
    try:
        url = f'{PROMO_BASE}/bonuses/product/{PRODUCT_ID}/partner/{PARTNER_ID}'
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data
    except Exception as e:
        log.debug(f'API check failed: {e}')
    return None


def update_tournament_status(tournament_id, updates):
    """Update tournament fields in database."""
    if not updates:
        return False

    conn = get_db_connection()
    cur = conn.cursor()

    set_clauses = []
    values = []
    for key, value in updates.items():
        set_clauses.append(f"{key} = %s")
        values.append(value)

    values.append(tournament_id)

    try:
        cur.execute(f"""
            UPDATE tournaments
            SET {', '.join(set_clauses)}, scraped_at = NOW()
            WHERE id = %s
        """, values)
        conn.commit()
        result = cur.rowcount > 0
    except Exception as e:
        log.error(f'Update error: {e}')
        conn.rollback()
        result = False

    cur.close()
    conn.close()
    return result


def mark_running_tournaments():
    """Check scheduled tournaments and mark them as running if started."""
    scheduled = get_scheduled_near_start()
    now = datetime.now()
    current_day = now.strftime('%A').lower()
    current_hour = now.hour
    current_minute = now.minute

    updated = 0
    for t in scheduled:
        schedule_day = t.get('schedule_day', '').lower()
        start_time = t.get('start_time', '')

        # Check if today matches schedule day
        if schedule_day and schedule_day == current_day:
            # Parse start time (e.g., "6:00 pm" or "18:00")
            try:
                if 'pm' in start_time.lower():
                    hour = int(start_time.split(':')[0])
                    if hour != 12:
                        hour += 12
                elif 'am' in start_time.lower():
                    hour = int(start_time.split(':')[0])
                    if hour == 12:
                        hour = 0
                else:
                    hour = int(start_time.split(':')[0])

                # If current time is past start time, mark as running
                if current_hour > hour or (current_hour == hour and current_minute >= 0):
                    update_tournament_status(t['id'], {'status': 'running'})
                    log.info(f"Marked tournament as running: {t['name']}")
                    updated += 1
            except (ValueError, IndexError):
                pass

    return updated


def track_active_tournaments():
    """Poll active tournaments for updates."""
    active = get_active_tournaments()

    if not active:
        log.info('No active tournaments to track')
        return 0

    log.info(f'Tracking {len(active)} active tournaments')

    updated = 0
    for t in active:
        # Try to fetch updated data
        api_data = check_tournament_status_api(t.get('external_id'))

        if api_data:
            # Parse and update tournament data
            updates = {}
            if 'players' in api_data:
                updates['players_registered'] = api_data['players']
            if 'prizePool' in api_data:
                updates['prize_pool_actual_zar'] = float(api_data['prizePool'])
            if 'status' in api_data:
                status_map = {
                    'RUNNING': 'running',
                    'LATE_REG': 'late_reg',
                    'FINISHED': 'finished',
                    'CANCELLED': 'cancelled'
                }
                updates['status'] = status_map.get(api_data['status'], api_data['status'])

            if updates and update_tournament_status(t['id'], updates):
                log.info(f"Updated tournament {t['name']}: {updates}")
                updated += 1

    return updated


def run_once():
    """Run a single tracking cycle."""
    log.info('Starting active tournament tracking cycle...')

    # First, check if any scheduled tournaments should be marked as running
    marked = mark_running_tournaments()
    if marked:
        log.info(f'Marked {marked} tournaments as running')

    # Then track active tournaments
    updated = track_active_tournaments()
    log.info(f'Cycle complete: {updated} tournaments updated')

    return updated


def main():
    """Main loop - track every 60 seconds."""
    log.info('Worker 2 (Active Tournament Tracker) starting...')

    while True:
        try:
            run_once()
        except Exception as e:
            log.error(f'Main loop error: {e}')

        log.info('Sleeping 60 seconds...')
        time.sleep(60)


if __name__ == '__main__':
    main()
