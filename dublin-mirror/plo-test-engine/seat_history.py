#!/usr/bin/env python3
"""
Seat state history tracking module for Phase 2
Maintains ring buffer of seat state changes
"""

import time

# Constants
MAX_HISTORY_ENTRIES = 100

def update_seat_history(history_dict, table_id, seat_index, snapshot, action_taken=None):
    """
    Track seat state changes in ring buffer
    
    Args:
        history_dict: Dictionary to store history (_seat_history)
        table_id: Table identifier
        seat_index: Seat position
        snapshot: Full table snapshot
        action_taken: Optional action that was executed
    """
    key = f"{table_id}:{seat_index}"
    now = time.time()
    
    # Find hero seat in snapshot
    hero_seat = None
    for s in snapshot.get('seats', []):
        if s.get('is_hero'):
            hero_seat = s
            break
    
    if not hero_seat:
        return
    
    # Create history entry
    entry = {
        'timestamp': now,
        'street': snapshot.get('street', 'PREFLOP'),
        'hole_cards': hero_seat.get('hole_cards', []),
        'stack_zar': hero_seat.get('stack_zar', 0),
        'status': hero_seat.get('status', 'empty'),
        'action_taken': action_taken,
        'pot_zar': snapshot.get('pot_zar', 0),
        'dealer_seat': snapshot.get('dealer_seat', 0),
    }
    
    if key in history_dict:
        # Existing history - append
        hist = history_dict[key]
        hist['history'].append(entry)
        
        # Enforce ring buffer limit
        if len(hist['history']) > MAX_HISTORY_ENTRIES:
            hist['history'] = hist['history'][-MAX_HISTORY_ENTRIES:]
        
        # Detect state change
        if hist['last_cards'] != entry['hole_cards']:
            hist['state_changes'] += 1
        
        hist['last_cards'] = entry['hole_cards']
        hist['last_update_time'] = now
        if action_taken:
            hist['last_action'] = action_taken
    else:
        # New history - initialize
        history_dict[key] = {
            'table_id': table_id,
            'seat_index': seat_index,
            'history': [entry],
            'last_action': action_taken,
            'last_cards': entry['hole_cards'],
            'last_update_time': now,
            'state_changes': 0,
        }

def get_seat_history(history_dict, table_id, seat_index, limit=50):
    """
    Get historical data for specific seat
    
    Args:
        history_dict: Dictionary storing history
        table_id: Table identifier
        seat_index: Seat position
        limit: Max entries to return
        
    Returns:
        List of history entries (most recent first)
    """
    key = f"{table_id}:{seat_index}"
    
    if key not in history_dict:
        return []
    
    hist = history_dict[key]
    # Return most recent entries (up to limit)
    return hist['history'][-limit:]

def get_state_changes(history_dict, table_id, seat_index):
    """
    Get number of state changes for a seat
    
    Returns:
        Integer count of detected state changes
    """
    key = f"{table_id}:{seat_index}"
    
    if key not in history_dict:
        return 0
    
    return history_dict[key].get('state_changes', 0)

def record_action(history_dict, seat_token, command_type, snapshot_store):
    """
    Record an action in the most recent history entry
    
    Args:
        history_dict: Dictionary storing history
        seat_token: Token identifying the seat
        command_type: Type of command executed
        snapshot_store: _snapshot_store to find table_id and seat_index
    """
    # Find seat by token
    for key, record in snapshot_store.items():
        if record.get('seat_token') == seat_token:
            table_id = record['table_id']
            seat_index = record['seat_index']
            hist_key = f"{table_id}:{seat_index}"
            
            if hist_key in history_dict:
                hist = history_dict[hist_key]
                hist['last_action'] = command_type
                if hist['history']:
                    hist['history'][-1]['action_taken'] = command_type
            break
