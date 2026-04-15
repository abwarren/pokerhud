#!/usr/bin/env python3
"""
Worker 5: Player Timeseries Ledger
==================================
Tracks player activity, balances, and status over time.
Records to Supabase player_timeseries table.
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from supabase import create_client, Client

# Supabase config
SUPABASE_URL = "https://kzqrdtagpykoylhuqcyv.supabase.co"
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', 
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt6cXJkdGFncHlrb3lsaHVxY3l2Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NjA3MzEwNCwiZXhwIjoyMDkxNjQ5MTA0fQ.y5VXs_spu14SiOU4R_uLHZS2j0BTy8_wHilUQD_0D-s')

# My Players (the 9 bot accounts)
MY_PLAYERS = [
    'kele1', 'kana', 'leni',
    'shax', 'pretty88', 'lont',
    'daniellek', 'pile', 'hele'
]

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [TIMESERIES] %(levelname)s - %(message)s'
)
log = logging.getLogger('timeseries')

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def record_player_status(supabase: Client, player_name: str, status_data: dict):
    """Record a player status entry to timeseries"""
    entry = {
        'player_name': player_name,
        'is_active': status_data.get('is_active', False),
        'balance_tc': status_data.get('balance_tc'),
        'balance_zar': status_data.get('balance_zar'),
        'balance_change': status_data.get('balance_change'),
        'table_name': status_data.get('table_name'),
        'seat_number': status_data.get('seat_number'),
        'status': status_data.get('status', 'unknown'),
        'site': status_data.get('site', 'pokerbet'),
        'session_id': status_data.get('session_id'),
        'hands_played': status_data.get('hands_played', 0),
        'metadata': json.dumps(status_data.get('metadata', {}))
    }
    
    result = supabase.table('player_timeseries').insert(entry).execute()
    return result

def get_latest_status(supabase: Client, player_name: str):
    """Get the most recent status for a player"""
    result = supabase.table('player_timeseries')\
        .select('*')\
        .eq('player_name', player_name)\
        .order('timestamp', desc=True)\
        .limit(1)\
        .execute()
    return result.data[0] if result.data else None

def get_active_players(supabase: Client):
    """Get all currently active players"""
    result = supabase.table('player_timeseries')\
        .select('player_name, timestamp, balance_tc, balance_zar, table_name, status')\
        .eq('is_active', True)\
        .order('timestamp', desc=True)\
        .execute()
    
    # Dedupe to get latest per player
    seen = set()
    active = []
    for row in result.data:
        if row['player_name'] not in seen:
            seen.add(row['player_name'])
            active.append(row)
    return active

def main():
    log.info("Starting Player Timeseries Ledger")
    supabase = get_supabase()
    
    # Example: Record initial status for all MY_PLAYERS
    for player in MY_PLAYERS:
        record_player_status(supabase, player, {
            'is_active': False,
            'status': 'initialized',
            'site': 'pokerbet'
        })
        log.info(f"Initialized {player}")
    
    log.info("All players initialized in timeseries")
    
    # In production, this would poll for real status updates
    # and record changes to the timeseries

if __name__ == '__main__':
    main()
