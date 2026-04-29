#!/usr/bin/env python3
"""
Admin debug dashboard routes for Phase 2
"""

import time
from flask import jsonify, request

def register_admin_routes(app, snapshot_store, bot_heartbeats, seat_history, command_queue, validation_errors, store_lock):
    """
    Register admin debug dashboard endpoints
    
    Args:
        app: Flask app instance
        snapshot_store: _snapshot_store reference
        bot_heartbeats: _bot_heartbeats reference
        seat_history: _seat_history reference
        command_queue: _command_queue reference
        validation_errors: _validation_errors reference
        store_lock: Thread lock
    """
    
    @app.route('/api/admin/debug', methods=['GET'])
    def admin_debug_dashboard():
        """
        Return comprehensive debug data for admin dashboard
        """
        now = time.time()
        
        with store_lock:
            # Bot heartbeats with real-time status
            heartbeats_list = []
            for hb in bot_heartbeats.values():
                age = now - hb['last_snapshot_time']
                if age < 2.0:
                    status = 'active'
                elif age < 10.0:
                    status = 'stale'
                else:
                    status = 'offline'
                
                heartbeats_list.append({
                    'table_id': hb['table_id'],
                    'seat_index': hb['seat_index'],
                    'bot_status': status,
                    'last_seen_ago': age,
                    'snapshot_count': hb['snapshot_count'],
                    'bot_name': hb['bot_name'],
                    'first_seen': hb['first_seen'],
                })
            
            # Recent snapshots (last 20)
            snapshot_list = []
            for rec in sorted(snapshot_store.values(), key=lambda r: r['last_seen'], reverse=True)[:20]:
                snapshot_list.append({
                    'table_id': rec['table_id'],
                    'seat_index': rec['seat_index'],
                    'timestamp': rec['last_seen'],
                    'age': now - rec['last_seen'],
                    'name': rec['name'],
                    'status': rec['status'],
                    'stack_zar': rec['stack_zar'],
                })
            
            # Validation errors (last 50)
            errors_list = validation_errors[-50:]
            
            # Last commands per seat
            commands_list = []
            for token, cmd in command_queue.items():
                if cmd:
                    # Find seat info from token
                    seat_info = None
                    for rec in snapshot_store.values():
                        if rec['seat_token'] == token:
                            seat_info = rec
                            break
                    
                    commands_list.append({
                        'seat_token': token[:8] + '...',
                        'table_id': seat_info['table_id'] if seat_info else 'unknown',
                        'seat_index': seat_info['seat_index'] if seat_info else -1,
                        'command_type': cmd['type'],
                        'status': cmd['status'],
                        'queued_at': cmd['queued_at'],
                        'age': now - cmd['queued_at'],
                    })
            
            # Active tables
            active_tables = set()
            for rec in snapshot_store.values():
                active_tables.add(rec['table_id'])
            
            debug_data = {
                'timestamp': now,
                'active_tables': list(active_tables),
                'active_table_count': len(active_tables),
                'total_bots': len(bot_heartbeats),
                'active_bots': len([h for h in heartbeats_list if h['bot_status'] == 'active']),
                'stale_bots': len([h for h in heartbeats_list if h['bot_status'] == 'stale']),
                'offline_bots': len([h for h in heartbeats_list if h['bot_status'] == 'offline']),
                'bot_heartbeats': heartbeats_list,
                'recent_snapshots': snapshot_list,
                'validation_errors': errors_list,
                'last_commands': commands_list,
            }
        
        return jsonify({'ok': True, 'debug': debug_data})
    
    @app.route('/api/admin/seat-history/<table_id>/<int:seat_index>', methods=['GET'])
    def get_seat_history_api(table_id, seat_index):
        """Get historical data for specific seat"""
        limit = request.args.get('limit', 50, type=int)
        history_key = f"{table_id}:{seat_index}"
        
        with store_lock:
            if history_key not in seat_history:
                return jsonify({
                    'ok': False,
                    'error': 'No history found for this seat'
                }), 404
            
            hist = seat_history[history_key]
            history_entries = hist['history'][-limit:]
            
            return jsonify({
                'ok': True,
                'table_id': table_id,
                'seat_index': seat_index,
                'last_action': hist.get('last_action'),
                'last_update_time': hist.get('last_update_time'),
                'state_changes': hist.get('state_changes', 0),
                'total_entries': len(hist['history']),
                'history': history_entries,
            })
    
    @app.route('/api/admin/stale-bots', methods=['GET'])
    def get_stale_bots():
        """Get list of stale or offline bots"""
        now = time.time()
        
        with store_lock:
            stale_list = []
            for hb in bot_heartbeats.values():
                age = now - hb['last_snapshot_time']
                if age < 2.0:
                    status = 'active'
                elif age < 10.0:
                    status = 'stale'
                else:
                    status = 'offline'
                
                if status != 'active':
                    stale_list.append({
                        'table_id': hb['table_id'],
                        'seat_index': hb['seat_index'],
                        'bot_status': status,
                        'last_seen_ago': age,
                        'bot_name': hb['bot_name'],
                    })
        
        return jsonify({
            'ok': True,
            'stale_bots': stale_list,
            'count': len(stale_list)
        })
