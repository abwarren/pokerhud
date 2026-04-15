#!/usr/bin/env python3
"""
Worker 4: ICM/Stack Snapshots
==============================
Captures live stack distributions and calculates ICM equity for running tournaments.
Polls every 30 seconds during active tournaments.
"""

import json
import time
import logging
import math
from datetime import datetime, timezone
from decimal import Decimal
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

# PokerBet API
PARTNER_ID = '18751019'
WS_URL = 'wss://poker-general.skillgames-bc.com'

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [ICM] %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/opt/pokerhud/logs/worker4_icm.log')
    ]
)
log = logging.getLogger('icm_snapshots')


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def get_active_tournaments():
    """Get currently running tournaments."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, name, external_id, prize_pool_guaranteed_zar,
               prize_pool_actual_zar, players_registered, players_max
        FROM tournaments
        WHERE status IN ('running', 'late_reg')
        ORDER BY scraped_at DESC
    """)
    tournaments = cur.fetchall()
    cur.close()
    conn.close()
    return tournaments


def get_latest_blind_level(tournament_id):
    """Get the most recent blind level for a tournament."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT level_number, small_blind, big_blind, ante
        FROM tournament_blind_levels
        WHERE tournament_id = %s
        ORDER BY level_number DESC
        LIMIT 1
    """, (tournament_id,))
    level = cur.fetchone()
    cur.close()
    conn.close()
    return level


def get_last_snapshot_time(tournament_id):
    """Get the timestamp of the last ICM snapshot."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT computed_at FROM tournament_icm_snapshots
        WHERE tournament_id = %s
        ORDER BY computed_at DESC
        LIMIT 1
    """, (tournament_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else None


def calculate_icm_equity(stacks, prize_pool, payout_structure):
    """
    Calculate ICM (Independent Chip Model) equity for each player.

    Uses Malmuth-Harville model for probability calculations.

    Args:
        stacks: dict of {player_name: chip_count}
        prize_pool: total prize pool in ZAR
        payout_structure: list of payout percentages [1st%, 2nd%, 3rd%, ...]

    Returns:
        dict of {player_name: equity_zar}
    """
    if not stacks or not prize_pool:
        return {}

    total_chips = sum(stacks.values())
    if total_chips == 0:
        return {}

    players = list(stacks.keys())
    n_players = len(players)

    # Default payout structure if not provided
    if not payout_structure or len(payout_structure) < n_players:
        # Standard payout: 50% 1st, 30% 2nd, 20% 3rd, then diminishing
        payout_structure = [50, 30, 20]
        remaining = 100 - sum(payout_structure)
        if n_players > 3:
            per_remaining = remaining / max(1, n_players - 3)
            payout_structure.extend([per_remaining] * (n_players - 3))

    # Normalize payouts to prize pool
    payouts = []
    for i in range(min(len(payout_structure), n_players)):
        payouts.append(prize_pool * payout_structure[i] / 100)

    # Calculate ICM equity using recursive probability
    equities = {player: 0.0 for player in players}

    def prob_finish(remaining_players, remaining_stacks, position, memo=None):
        """Calculate probability of finishing in a given position."""
        if memo is None:
            memo = {}

        key = (tuple(sorted(remaining_players)), position)
        if key in memo:
            return memo[key]

        total = sum(remaining_stacks[p] for p in remaining_players)
        if total == 0:
            return {p: 1.0 / len(remaining_players) for p in remaining_players}

        if position == 1 or len(remaining_players) == 1:
            # First place probability is proportional to chip count
            result = {p: remaining_stacks[p] / total for p in remaining_players}
        else:
            result = {}
            for player in remaining_players:
                prob = 0.0
                # Player finishes here if someone else wins and player finishes (position-1) among rest
                for winner in remaining_players:
                    if winner == player:
                        continue
                    win_prob = remaining_stacks[winner] / total
                    others = [p for p in remaining_players if p != winner]
                    if len(others) > 0:
                        sub_probs = prob_finish(tuple(others), remaining_stacks, position - 1, memo)
                        prob += win_prob * sub_probs.get(player, 0)
                result[player] = prob

        memo[key] = result
        return result

    # Calculate equity for each position
    for pos in range(1, min(len(payouts) + 1, n_players + 1)):
        probs = prob_finish(tuple(players), stacks, pos)
        payout = payouts[pos - 1] if pos <= len(payouts) else 0
        for player, prob in probs.items():
            equities[player] += prob * payout

    return equities


def generate_hand_id(tournament_id, timestamp):
    """Generate a unique hand ID for the snapshot."""
    ts = timestamp.strftime('%Y%m%d_%H%M%S')
    return f"icm_{tournament_id}_{ts}"


def save_icm_snapshot(tournament, stacks, equities, blind_level=None):
    """Save ICM snapshot to database."""
    conn = get_db_connection()
    cur = conn.cursor()

    hand_id = generate_hand_id(
        tournament['id'],
        datetime.now(timezone.utc)
    )

    prize_pool = tournament.get('prize_pool_actual_zar') or tournament.get('prize_pool_guaranteed_zar')

    blind_str = None
    sb = None
    bb = None
    if blind_level:
        sb = blind_level.get('small_blind')
        bb = blind_level.get('big_blind')
        blind_str = f"Level {blind_level.get('level_number', '?')}: {sb}/{bb}"

    try:
        cur.execute('''
            INSERT INTO tournament_icm_snapshots (
                tournament_id, hand_id, tournament_name, blind_level,
                small_blind, big_blind, players_remaining, total_chips,
                prize_pool_zar, stacks, equities, method, computed_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            ON CONFLICT (hand_id) DO UPDATE SET
                stacks = EXCLUDED.stacks,
                equities = EXCLUDED.equities,
                computed_at = NOW()
        ''', (
            tournament['id'],
            hand_id,
            tournament['name'],
            blind_str,
            sb,
            bb,
            len(stacks),
            sum(stacks.values()),
            prize_pool,
            json.dumps(stacks),
            json.dumps(equities),
            'icm_worker'
        ))
        conn.commit()
        result = True
    except Exception as e:
        log.error(f'Error saving ICM snapshot: {e}')
        conn.rollback()
        result = False

    cur.close()
    conn.close()
    return result


def save_blind_level(tournament_id, level_number, small_blind, big_blind, ante=0, duration=None):
    """Save blind level to database."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute('''
            INSERT INTO tournament_blind_levels (
                tournament_id, level_number, small_blind, big_blind,
                ante, duration_minutes, observed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (tournament_id, level_number) DO UPDATE SET
                small_blind = EXCLUDED.small_blind,
                big_blind = EXCLUDED.big_blind,
                ante = EXCLUDED.ante,
                observed_at = NOW()
        ''', (tournament_id, level_number, small_blind, big_blind, ante, duration))
        conn.commit()
        result = True
    except Exception as e:
        log.error(f'Error saving blind level: {e}')
        conn.rollback()
        result = False

    cur.close()
    conn.close()
    return result


def fetch_live_stacks(tournament):
    """
    Fetch live stack data from the poker platform.

    Note: This is a placeholder. Real implementation would:
    1. Connect to WebSocket wss://poker-general.skillgames-bc.com
    2. Subscribe to tournament updates
    3. Parse stack data from messages

    For now, we simulate with the data we can gather from REST APIs.
    """
    # In production, this would connect to WebSocket and get real-time data
    # For now, return empty to indicate no live data available
    return {}


def simulate_stacks_for_testing(tournament):
    """
    Generate simulated stack data for testing ICM calculations.
    Only used when no live data is available.
    """
    import random

    players = tournament.get('players_registered', 9) or 9
    if players < 2:
        players = 9

    # Generate random stack distribution
    starting_stack = 3000  # Standard starting stack
    total_chips = starting_stack * players

    stacks = {}
    remaining = total_chips
    for i in range(players - 1):
        # Random stack between 500 and remaining - 500*remaining_players
        min_stack = 500
        max_stack = remaining - (min_stack * (players - i - 1))
        stack = random.randint(min_stack, max(min_stack, max_stack))
        stacks[f'Player{i+1}'] = stack
        remaining -= stack

    stacks[f'Player{players}'] = remaining
    return stacks


def run_once():
    """Run a single ICM snapshot cycle."""
    log.info('Starting ICM snapshot cycle...')

    tournaments = get_active_tournaments()

    if not tournaments:
        log.info('No active tournaments to snapshot')
        return 0

    snapshots_created = 0

    for t in tournaments:
        # Check if we recently took a snapshot (avoid spamming)
        last_snap = get_last_snapshot_time(t['id'])
        if last_snap:
            elapsed = (datetime.now(timezone.utc) - last_snap.replace(tzinfo=timezone.utc)).seconds
            if elapsed < 25:  # At least 25 seconds between snapshots
                continue

        # Try to fetch live stacks
        stacks = fetch_live_stacks(t)

        # If no live data, skip (or use simulated for testing)
        if not stacks:
            # Uncomment below line to use simulated data for testing:
            # stacks = simulate_stacks_for_testing(t)
            continue

        if len(stacks) < 2:
            continue

        # Get current blind level
        blind_level = get_latest_blind_level(t['id'])

        # Get prize pool
        prize_pool = t.get('prize_pool_actual_zar') or t.get('prize_pool_guaranteed_zar') or 0

        if prize_pool <= 0:
            continue

        # Calculate ICM equity
        # Default payout structure for 9-player STT
        payout_structure = [50, 30, 20]  # Top 3 paid
        equities = calculate_icm_equity(stacks, prize_pool, payout_structure)

        # Save snapshot
        if save_icm_snapshot(t, stacks, equities, blind_level):
            log.info(f"ICM snapshot saved for {t['name']}: {len(stacks)} players")
            snapshots_created += 1

    log.info(f'Cycle complete: {snapshots_created} ICM snapshots created')
    return snapshots_created


def main():
    """Main loop - snapshot every 30 seconds."""
    log.info('Worker 4 (ICM Snapshots) starting...')

    while True:
        try:
            run_once()
        except Exception as e:
            log.error(f'Main loop error: {e}')

        log.info('Sleeping 30 seconds...')
        time.sleep(30)


if __name__ == '__main__':
    main()
