#!/usr/bin/env python3
"""
Heartbeat tracking module for Phase 2
Monitors bot connection status based on snapshot timing
"""

import time

# Constants
STALE_THRESHOLD_SECONDS = 2.0
OFFLINE_THRESHOLD_SECONDS = 10.0

def check_bot_staleness(heartbeat):
    """
    Determine bot status based on last snapshot time
    Returns: 'active' | 'stale' | 'offline'
    """
    if not heartbeat:
        return 'offline'
    
    age = time.time() - heartbeat['last_snapshot_time']
    
    if age < STALE_THRESHOLD_SECONDS:
        return 'active'
    elif age < OFFLINE_THRESHOLD_SECONDS:
        return 'stale'
    else:
        return 'offline'

def update_heartbeat(heartbeats_dict, table_id, seat_index, seat_token, seat_name, hole_cards):
    """
    Update bot heartbeat tracking
    
    Args:
        heartbeats_dict: Dictionary to store heartbeats (_bot_heartbeats)
        table_id: Table identifier
        seat_index: Seat position (0-8)
        seat_token: Authentication token for this seat
        seat_name: Player/bot name
        hole_cards: Current hole cards (for change detection)
    """
    key = f"{table_id}:{seat_index}"
    now = time.time()
    
    if key in heartbeats_dict:
        # Existing bot - update
        hb = heartbeats_dict[key]
        hb['last_snapshot_time'] = now
        hb['snapshot_count'] += 1
        hb['last_cards'] = hole_cards
        hb['bot_name'] = seat_name
    else:
        # New bot - initialize
        heartbeats_dict[key] = {
            'table_id': table_id,
            'seat_index': seat_index,
            'seat_token': seat_token,
            'last_snapshot_time': now,
            'snapshot_count': 1,
            'bot_status': 'active',
            'last_cards': hole_cards,
            'first_seen': now,
            'bot_name': seat_name,
        }
    
    # Update status
    heartbeats_dict[key]['bot_status'] = check_bot_staleness(heartbeats_dict[key])

def get_stale_bots(heartbeats_dict):
    """
    Get list of stale or offline bots
    Returns list of bot records with status != 'active'
    """
    stale_bots = []
    
    for hb in heartbeats_dict.values():
        # Update status in real-time
        current_status = check_bot_staleness(hb)
        if current_status != 'active':
            stale_bots.append({
                'table_id': hb['table_id'],
                'seat_index': hb['seat_index'],
                'bot_status': current_status,
                'last_seen_ago': time.time() - hb['last_snapshot_time'],
                'bot_name': hb['bot_name'],
            })
    
    return stale_bots

def refresh_all_statuses(heartbeats_dict):
    """
    Update bot_status for all heartbeats based on current time
    Call this periodically or before returning heartbeat data
    """
    for hb in heartbeats_dict.values():
        hb['bot_status'] = check_bot_staleness(hb)
