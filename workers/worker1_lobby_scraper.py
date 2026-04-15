#!/usr/bin/env python3
"""
Worker 1: Lobby Scraper
=======================
Scrapes PokerBet tournament lobby for available/upcoming tournaments.
Runs every 5 minutes to discover new tournaments.
"""

import json
import re
import time
import logging
from datetime import datetime, timezone
from html import unescape
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

# PokerBet CMS endpoints
PARTNER_ID = '18751019'
CMS_BASE = 'https://go-cms.pokerbet.co.za/api/public/v1/eng/partners'

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [LOBBY] %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/opt/pokerhud/logs/worker1_lobby.log')
    ]
)
log = logging.getLogger('lobby_scraper')

# Poker keywords for filtering
POKER_KEYWORDS = [
    'tournament', 'slam', 'satellite', 'freeroll', 'buy-in', 'guarantee',
    'omaha', 'holdem', "hold'em", 'nlhe', 'plo', 'poker', 'rakeback',
    'sit & go', 'sit and go', 'bounty', 'freezeout', 'rebuy', 'turbo'
]

NON_POKER = [
    'sport welcome', 'casino welcome', 'cricket', 'rugby', 'soccer',
    'slots', 'roulette', 'blackjack', 'motorsport', 'basketball'
]


def strip_html(text):
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', unescape(text)).strip()


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def scrape_promotions():
    """Scrape CMS promotions for tournament info."""
    tournaments = []
    try:
        url = f'{CMS_BASE}/{PARTNER_ID}/promotions'
        params = {'use_webp': '1', 'platform': '0', 'category': 'poker', 'country': 'ZA'}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        items = data.get('data', []) if isinstance(data, dict) else data
        if isinstance(items, dict):
            items = list(items.values())
            if items and isinstance(items[0], list):
                items = items[0]

        for item in items:
            if not isinstance(item, dict):
                continue

            title = item.get('title', '')
            content = strip_html(item.get('content', ''))
            title_lower = title.lower()

            # Filter non-poker
            if any(ind in title_lower for ind in NON_POKER):
                continue
            if not any(kw in title_lower for kw in POKER_KEYWORDS):
                continue

            full_text = f'{title} {content}'.lower()

            t = {
                'site': 'pokerbet',
                'source': 'cms_lobby',
                'external_id': str(item.get('id', '')),
                'name': title,
                'description': content[:500],
                'image_url': item.get('src', ''),
                'raw_data': json.dumps(item),
                'status': 'scheduled'
            }

            # Parse buy-in
            buyin_match = re.search(r'R\s?(\d+)\s*\+\s*R\s?(\d+)', content)
            if buyin_match:
                t['buy_in_entry_zar'] = float(buyin_match.group(1))
                t['buy_in_fee_zar'] = float(buyin_match.group(2))
                t['buy_in_total_zar'] = t['buy_in_entry_zar'] + t['buy_in_fee_zar']

            # Parse guarantee
            gtd_match = re.search(r'(?:guarantee|guaranteed)[^R]*R\s?([\d,]+)', full_text, re.I)
            if gtd_match:
                t['prize_pool_guaranteed_zar'] = float(gtd_match.group(1).replace(',', ''))

            # Parse schedule
            for day in ['sunday', 'saturday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
                if day in full_text:
                    t['schedule_day'] = day
                    break

            # Parse time
            time_match = re.search(r'(\d{1,2})[:.]?(\d{2})\s*(am|pm)', full_text)
            if time_match:
                t['start_time'] = f"{time_match.group(1)}:{time_match.group(2)} {time_match.group(3)}"

            # Game type
            if 'omaha' in full_text or 'plo' in full_text:
                t['game_type'] = 'PLO'
            elif 'hold' in full_text or 'nlhe' in full_text:
                t['game_type'] = 'NLHE'

            # Satellite detection
            if 'satellite' in full_text:
                t['is_satellite'] = True

            tournaments.append(t)

        log.info(f'Found {len(tournaments)} poker tournaments from CMS')
    except Exception as e:
        log.error(f'Scrape error: {e}')

    return tournaments


def save_tournaments(tournaments):
    """Upsert tournaments to PostgreSQL."""
    if not tournaments:
        return 0

    conn = get_db_connection()
    cur = conn.cursor()
    saved = 0

    for t in tournaments:
        try:
            # Use ON CONFLICT to upsert
            cur.execute('''
                INSERT INTO tournaments (
                    site, source, external_id, name, description, image_url,
                    buy_in_entry_zar, buy_in_fee_zar, buy_in_total_zar,
                    prize_pool_guaranteed_zar, schedule_day, start_time,
                    game_type, is_satellite, status, raw_data, scraped_at
                ) VALUES (
                    %(site)s, %(source)s, %(external_id)s, %(name)s, %(description)s, %(image_url)s,
                    %(buy_in_entry_zar)s, %(buy_in_fee_zar)s, %(buy_in_total_zar)s,
                    %(prize_pool_guaranteed_zar)s, %(schedule_day)s, %(start_time)s,
                    %(game_type)s, %(is_satellite)s, %(status)s, %(raw_data)s, NOW()
                )
                ON CONFLICT (site, name, source, start_time)
                DO UPDATE SET
                    description = EXCLUDED.description,
                    buy_in_entry_zar = COALESCE(EXCLUDED.buy_in_entry_zar, tournaments.buy_in_entry_zar),
                    buy_in_fee_zar = COALESCE(EXCLUDED.buy_in_fee_zar, tournaments.buy_in_fee_zar),
                    buy_in_total_zar = COALESCE(EXCLUDED.buy_in_total_zar, tournaments.buy_in_total_zar),
                    prize_pool_guaranteed_zar = COALESCE(EXCLUDED.prize_pool_guaranteed_zar, tournaments.prize_pool_guaranteed_zar),
                    raw_data = EXCLUDED.raw_data,
                    scraped_at = NOW()
            ''', {
                'site': t.get('site', 'pokerbet'),
                'source': t.get('source', 'cms_lobby'),
                'external_id': t.get('external_id'),
                'name': t.get('name'),
                'description': t.get('description', ''),
                'image_url': t.get('image_url', ''),
                'buy_in_entry_zar': t.get('buy_in_entry_zar'),
                'buy_in_fee_zar': t.get('buy_in_fee_zar'),
                'buy_in_total_zar': t.get('buy_in_total_zar'),
                'prize_pool_guaranteed_zar': t.get('prize_pool_guaranteed_zar'),
                'schedule_day': t.get('schedule_day'),
                'start_time': t.get('start_time'),
                'game_type': t.get('game_type'),
                'is_satellite': t.get('is_satellite', False),
                'status': t.get('status', 'scheduled'),
                'raw_data': t.get('raw_data')
            })
            saved += 1
        except Exception as e:
            log.error(f"Error saving tournament {t.get('name')}: {e}")
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()
    return saved


def run_once():
    """Run a single scrape cycle."""
    log.info('Starting lobby scrape cycle...')
    tournaments = scrape_promotions()
    saved = save_tournaments(tournaments)
    log.info(f'Cycle complete: {saved} tournaments saved/updated')
    return saved


def main():
    """Main loop - scrape every 5 minutes."""
    log.info('Worker 1 (Lobby Scraper) starting...')

    while True:
        try:
            run_once()
        except Exception as e:
            log.error(f'Main loop error: {e}')

        log.info('Sleeping 5 minutes...')
        time.sleep(300)


if __name__ == '__main__':
    main()
