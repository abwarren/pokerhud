#!/usr/bin/env python3
"""
FLOP Auto-Trigger Service (v1.1.0)

Monitors collector output and auto-triggers equity engine on flop detection.

Rules:
- FLOP (3 cards) → AUTO run once per flop
- RIVER (5 cards) → RESET state
- One batch = one table snapshot
"""

import time
import requests
import hashlib
from datetime import datetime

# Configuration
COLLECTOR_API = 'http://localhost:5000/api/collector/latest'
ENGINE_API = 'http://localhost:5002/api/run'
POLL_INTERVAL = 1.5  # seconds
RESET_ON_RIVER = True

# State tracking
last_snapshot_hash = ''
last_flop = ''
last_board_size = 0
is_running = False

def log(msg):
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}')

def extract_board_size(text):
    """Detect board size from batch text. Only FLOP (6 chars) and RIVER (10 chars)."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    for line in lines:
        if len(line) == 6:
            return 3  # FLOP
        if len(line) == 10:
            return 5  # RIVER

    return 0  # No board / preflop

def extract_flop(text):
    """Extract 3-card flop from batch."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines:
        if len(line) == 6:
            return line
    return None

def extract_players(text):
    """Extract player hands from batch."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    return [l for l in lines if len(l) in (8, 10, 12, 14)]

def trigger_engine(batch_text):
    """Send batch to equity engine API."""
    global is_running

    try:
        is_running = True
        log(f'→ Triggering engine with batch ({len(batch_text)} chars)')

        response = requests.post(
            ENGINE_API,
            json={'text': batch_text},
            timeout=30
        )

        if response.status_code == 200:
            log('✓ Engine run successful')
            return True
        else:
            log(f'✗ Engine error: {response.status_code} - {response.text[:100]}')
            return False

    except Exception as e:
        log(f'✗ Engine call failed: {e}')
        return False
    finally:
        is_running = False

def process_snapshot(text):
    """Process collector snapshot and maybe trigger engine."""
    global last_snapshot_hash, last_flop, last_board_size

    # Hash guard
    snapshot_hash = hashlib.md5(text.encode()).hexdigest()
    if snapshot_hash == last_snapshot_hash:
        return  # No change

    last_snapshot_hash = snapshot_hash

    # Extract data
    board_size = extract_board_size(text)
    flop = extract_flop(text)
    players = extract_players(text)

    log(f'Snapshot: {len(players)} players, board_size={board_size}')

    # RIVER RESET
    if board_size == 5 and RESET_ON_RIVER:
        log('RIVER detected → RESET state')
        last_flop = ''
        last_board_size = 0
        return

    # FLOP TRIGGER
    if board_size == 3:
        if flop and flop != last_flop:
            if len(players) >= 6:
                if not is_running:
                    log(f'✓ FLOP detected: {flop} with {len(players)} players → AUTO-RUN')
                    last_flop = flop
                    last_board_size = board_size
                    trigger_engine(text)
                else:
                    log('Already running, skip trigger')
            else:
                log(f'Not enough players ({len(players)}/6), skip trigger')
        else:
            log(f'Duplicate flop or no flop detected, skip')
    elif board_size == 0:
        log('PREFLOP → waiting for flop')

    last_board_size = board_size

def main():
    log('=== FLOP Auto-Trigger Service v1.1.0 ===')
    log(f'Collector: {COLLECTOR_API}')
    log(f'Engine: {ENGINE_API}')
    log(f'Poll interval: {POLL_INTERVAL}s')
    log(f'Rule: Auto-run on FLOP (3 cards), once per flop')
    log('')

    consecutive_errors = 0

    while True:
        try:
            # Poll collector
            response = requests.get(COLLECTOR_API, timeout=5)

            if response.status_code == 200:
                consecutive_errors = 0
                data = response.json()
                text = data.get('raw', '')

                if text:
                    process_snapshot(text)
                else:
                    log('Empty snapshot')
            else:
                consecutive_errors += 1
                log(f'Collector error: {response.status_code} (errors: {consecutive_errors})')

        except KeyboardInterrupt:
            log('Shutting down...')
            break
        except Exception as e:
            consecutive_errors += 1
            log(f'Error: {e} (consecutive: {consecutive_errors})')

            if consecutive_errors >= 10:
                log('Too many errors, backing off 30s')
                time.sleep(30)
                consecutive_errors = 0

        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
