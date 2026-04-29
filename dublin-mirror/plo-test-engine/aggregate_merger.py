#!/usr/bin/env python3
"""
Aggregate merge logic for Phase 2
Merges snapshots from multiple bots showing only visible cards
"""

import time

def merge_table_aggregate(snapshot_store, bot_heartbeats, command_queue, table_id, cluster_id=None):
    """
    Build aggregate view merging multiple bot snapshots
    Shows only visible cards (hero cards + community cards)
    
    Args:
        snapshot_store: _snapshot_store dictionary
        bot_heartbeats: _bot_heartbeats dictionary
        command_queue: _command_queue dictionary
        table_id: Table to merge
        cluster_id: Optional cluster filter
        
    Returns:
        Aggregate table dict or None
    """
    now = time.time()
    
    # Collect all seats for this table
    seat_records = []
    for store_key, record in snapshot_store.items():
        if record['table_id'] == table_id:
            # Apply cluster filter if specified
            if cluster_id:
                snap_cluster = record['last_snapshot'].get('cluster_id')
                if snap_cluster != cluster_id:
                    continue
            seat_records.append(record)
    
    if not seat_records:
        return None
    
    # Use most recent snapshot for table-level data (board, pot, etc.)
    latest_record = max(seat_records, key=lambda r: r['last_seen'])
    snap = latest_record['last_snapshot']
    
    # Build aggregate seats - group by seat_index
    seats_dict = {}
    bot_counts = {}  # Track how many bots report each seat
    
    for record in seat_records:
        seat_idx = record['seat_index']
        snap_seat = None
        
        # Find this seat in the snapshot
        for s in record['last_snapshot']['seats']:
            if s['seat_index'] == seat_idx:
                snap_seat = s
                break
        
        if snap_seat:
            # Get bot status from heartbeat
            hb_key = f"{table_id}:{seat_idx}"
            bot_status = 'unknown'
            if hb_key in bot_heartbeats:
                hb = bot_heartbeats[hb_key]
                age = now - hb['last_snapshot_time']
                if age < 2.0:
                    bot_status = 'active'
                elif age < 10.0:
                    bot_status = 'stale'
                else:
                    bot_status = 'offline'
            
            # Check for pending command
            pending_cmd = None
            cmd = command_queue.get(record['seat_token'])
            if cmd and cmd.get('status') == 'pending':
                pending_cmd = cmd['type']
            
            # CRITICAL: Only show cards if this is hero seat
            # DO NOT add face-down or villain cards
            hole_cards = []
            cards_visible = False
            if snap_seat.get('is_hero'):
                hole_cards = snap_seat.get('hole_cards', [])
                cards_visible = len(hole_cards) > 0
            
            # Track bot count for this seat
            bot_counts[seat_idx] = bot_counts.get(seat_idx, 0) + 1
            
            # Use most recent data for this seat
            if seat_idx not in seats_dict or record['last_seen'] > seats_dict[seat_idx].get('_last_seen', 0):
                seats_dict[seat_idx] = {
                    'seat_index': seat_idx,
                    'name': snap_seat.get('name') or f"Player {seat_idx + 1}",
                    'stack_zar': snap_seat.get('stack_zar'),
                    'hole_cards': hole_cards,
                    'cards_visible': cards_visible,
                    'status': snap_seat.get('status', 'empty'),
                    'is_dealer': snap_seat.get('is_dealer', False),
                    'bot_count': 1,  # Will be updated below
                    'bot_status': bot_status,
                    'last_seen_ago': now - record['last_seen'],
                    'pending_cmd': pending_cmd,
                    '_last_seen': record['last_seen'],  # Internal tracking
                }
    
    # Update bot counts
    for seat_idx, count in bot_counts.items():
        if seat_idx in seats_dict:
            seats_dict[seat_idx]['bot_count'] = count
    
    # Fill in empty seats from table structure (show all 9 seats)
    for s in snap.get('seats', []):
        if s['seat_index'] not in seats_dict:
            seats_dict[s['seat_index']] = {
                'seat_index': s['seat_index'],
                'name': s.get('name') or None,
                'stack_zar': s.get('stack_zar'),
                'hole_cards': [],
                'cards_visible': False,
                'status': s.get('status', 'empty'),
                'is_dealer': s.get('is_dealer', False),
                'bot_count': 0,
                'bot_status': 'offline',
                'last_seen_ago': None,
                'pending_cmd': None,
            }
    
    # Sort seats by index
    sorted_seats = sorted(seats_dict.values(), key=lambda s: s['seat_index'])
    
    # Remove internal tracking field
    for seat in sorted_seats:
        seat.pop('_last_seen', None)
    
    # Build aggregate table
    aggregate = {
        'table_id': table_id,
        'cluster_id': cluster_id,
        'variant': snap.get('variant', 'plo'),
        'street': snap.get('street', 'PREFLOP'),
        'pot_zar': snap.get('pot_zar'),
        'dealer_seat': snap.get('dealer_seat'),
        'board': snap.get('board', {'flop': [], 'turn': None, 'river': None}),
        'last_updated': now,
        'active_bots': len([s for s in sorted_seats if s['bot_status'] == 'active']),
        'total_bots': len(seat_records),
        'seats': sorted_seats,
    }
    
    return aggregate

def get_latest_aggregate(snapshot_store, bot_heartbeats, command_queue):
    """
    Get most recently updated aggregate table
    
    Returns:
        Aggregate table dict or None
    """
    # Find all unique table_ids
    table_ids = set()
    for record in snapshot_store.values():
        table_ids.add(record['table_id'])
    
    if not table_ids:
        return None
    
    # Build aggregates for all tables
    aggregates = []
    for table_id in table_ids:
        agg = merge_table_aggregate(snapshot_store, bot_heartbeats, command_queue, table_id)
        if agg:
            aggregates.append(agg)
    
    if not aggregates:
        return None
    
    # Return most recently updated
    return max(aggregates, key=lambda t: t['last_updated'])
