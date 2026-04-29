#!/usr/bin/env python3
"""
Data models and schemas for Phase 2 features
"""

# Heartbeat record schema
HEARTBEAT_RECORD_SCHEMA = {
    'table_id': str,
    'seat_index': int,
    'seat_token': str,
    'last_snapshot_time': float,  # Unix timestamp
    'snapshot_count': int,
    'bot_status': str,  # 'active' | 'stale' | 'offline'
    'last_cards': list,  # For change detection
    'first_seen': float,
    'bot_name': str,  # Extracted from snapshot
}

# Seat history record schema
SEAT_HISTORY_RECORD_SCHEMA = {
    'table_id': str,
    'seat_index': int,
    'history': list,  # Ring buffer, max 100 entries
    'last_action': str,  # or None
    'last_cards': list,
    'last_update_time': float,
    'state_changes': int,  # Counter for analytics
}

# History entry schema (element of history list)
HISTORY_ENTRY_SCHEMA = {
    'timestamp': float,
    'street': str,
    'hole_cards': list,
    'stack_zar': float,
    'status': str,
    'action_taken': str,  # or None
    'pot_zar': float,
    'dealer_seat': int,
}

# Aggregate seat schema
AGGREGATE_SEAT_SCHEMA = {
    'seat_index': int,
    'name': str,
    'stack_zar': float,
    'hole_cards': list,  # Only if this seat has a controlling bot
    'cards_visible': bool,
    'status': str,
    'is_dealer': bool,
    'bot_count': int,  # Number of bots reporting this seat
    'bot_status': str,  # 'active', 'stale', 'offline'
    'last_seen_ago': float,
    'pending_cmd': str,  # or None
}

# Validation error record
VALIDATION_ERROR_SCHEMA = {
    'timestamp': float,
    'error_type': str,
    'message': str,
    'table_id': str,  # or None
    'seat_index': int,  # or None
}
