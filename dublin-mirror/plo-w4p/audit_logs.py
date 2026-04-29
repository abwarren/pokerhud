"""
Audit Logging Module for PLO Remote Control
Non-blocking audit trail for user activity and ZAR ledger
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
import traceback

# Database path
DB_PATH = '/opt/plo-w4p/database.db'

# Fallback log files (if DB fails)
USER_AUDIT_LOG = Path('/opt/plo-w4p/logs/user_audit_log.jsonl')
ZAR_LEDGER_LOG = Path('/opt/plo-w4p/logs/zar_ledger_log.jsonl')


def get_db_connection():
    """Get SQLite database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_audit_tables():
    """Initialize audit tables - idempotent, non-blocking"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # ZAR Ledger table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS zar_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                username TEXT,
                user_id INTEGER,
                table_id TEXT,
                hand_id_previous TEXT,
                hand_id_current TEXT,
                previous_total_zar REAL,
                current_total_zar REAL,
                zar_delta REAL,
                direction TEXT,
                notes TEXT,
                metadata_json TEXT
            )
        ''')

        conn.commit()
        conn.close()
        print('[AUDIT] ZAR ledger table initialized')
        return True
    except Exception as e:
        print(f'[AUDIT] Table init failed (non-blocking): {e}')
        return False


def _write_jsonl_fallback(log_file, data):
    """Write to JSONL fallback if database fails"""
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'a') as f:
            f.write(json.dumps(data) + '\n')
        return True
    except Exception as e:
        print(f'[AUDIT] JSONL fallback failed: {e}')
        return False


# ══════════════════════════════════════════════════════════════════════════════
# USER ACTIVITY AUDIT (Login/Logout)
# ══════════════════════════════════════════════════════════════════════════════

def log_login_success(username, user_id=None, ip_address=None, user_agent=None):
    """
    Log successful login (non-blocking)

    Args:
        username: Username
        user_id: User ID (optional)
        ip_address: IP address (optional)
        user_agent: User agent string (optional)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO user_logs
            (timestamp, user_id, username, action, status, ip_address, user_agent)
            VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, 'LOGIN_SUCCESS', 'success', ip_address, user_agent))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f'[AUDIT] log_login_success failed (non-blocking): {e}')
        # Fallback to JSONL
        return _write_jsonl_fallback(USER_AUDIT_LOG, {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'username': username,
            'action': 'LOGIN_SUCCESS',
            'status': 'success',
            'ip_address': ip_address,
            'user_agent': user_agent
        })


def log_login_failed(username, ip_address=None, user_agent=None, reason=None):
    """
    Log failed login attempt (non-blocking)

    Args:
        username: Attempted username
        ip_address: IP address (optional)
        user_agent: User agent string (optional)
        reason: Failure reason (optional)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        details = json.dumps({'reason': reason}) if reason else None

        cursor.execute('''
            INSERT INTO user_logs
            (timestamp, username, action, status, ip_address, user_agent, details_json)
            VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)
        ''', (username, 'LOGIN_FAILED', 'failure', ip_address, user_agent, details))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f'[AUDIT] log_login_failed failed (non-blocking): {e}')
        # Fallback to JSONL
        return _write_jsonl_fallback(USER_AUDIT_LOG, {
            'timestamp': datetime.now().isoformat(),
            'username': username,
            'action': 'LOGIN_FAILED',
            'status': 'failure',
            'ip_address': ip_address,
            'user_agent': user_agent,
            'reason': reason
        })


def log_logout(username, user_id=None, ip_address=None):
    """
    Log user logout (non-blocking)

    Args:
        username: Username
        user_id: User ID (optional)
        ip_address: IP address (optional)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO user_logs
            (timestamp, user_id, username, action, status, ip_address)
            VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?)
        ''', (user_id, username, 'LOGOUT', 'success', ip_address))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f'[AUDIT] log_logout failed (non-blocking): {e}')
        # Fallback to JSONL
        return _write_jsonl_fallback(USER_AUDIT_LOG, {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'username': username,
            'action': 'LOGOUT',
            'status': 'success',
            'ip_address': ip_address
        })


# ══════════════════════════════════════════════════════════════════════════════
# ZAR LEDGER (Hand-to-Hand Tracking)
# ══════════════════════════════════════════════════════════════════════════════

def log_zar_change(
    username,
    current_total_zar,
    previous_total_zar,
    user_id=None,
    table_id=None,
    hand_id_current=None,
    hand_id_previous=None,
    notes=None,
    metadata=None
):
    """
    Log hand-to-hand ZAR change (non-blocking)

    Args:
        username: Username or account identifier
        current_total_zar: Current total ZAR after hand
        previous_total_zar: Previous total ZAR before hand
        user_id: User ID (optional)
        table_id: Table identifier (optional)
        hand_id_current: Current hand ID (optional)
        hand_id_previous: Previous hand ID (optional)
        notes: Additional notes (optional)
        metadata: Additional metadata dict (optional)

    Returns:
        dict: Ledger entry with calculated delta and direction
    """
    try:
        # Calculate delta
        zar_delta = current_total_zar - previous_total_zar

        # Determine direction
        if zar_delta > 0:
            direction = 'WIN'
        elif zar_delta < 0:
            direction = 'LOSS'
        else:
            direction = 'FLAT'

        metadata_json = json.dumps(metadata) if metadata else None

        # Write to database
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO zar_ledger
            (timestamp, username, user_id, table_id, hand_id_previous, hand_id_current,
             previous_total_zar, current_total_zar, zar_delta, direction, notes, metadata_json)
            VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (username, user_id, table_id, hand_id_previous, hand_id_current,
              previous_total_zar, current_total_zar, zar_delta, direction, notes, metadata_json))

        conn.commit()
        conn.close()

        return {
            'timestamp': datetime.now().isoformat(),
            'username': username,
            'zar_delta': zar_delta,
            'direction': direction,
            'current_total': current_total_zar,
            'previous_total': previous_total_zar
        }
    except Exception as e:
        print(f'[AUDIT] log_zar_change failed (non-blocking): {e}')
        traceback.print_exc()

        # Fallback to JSONL
        try:
            zar_delta = current_total_zar - previous_total_zar
            direction = 'WIN' if zar_delta > 0 else ('LOSS' if zar_delta < 0 else 'FLAT')

            entry = {
                'timestamp': datetime.now().isoformat(),
                'username': username,
                'user_id': user_id,
                'table_id': table_id,
                'hand_id_previous': hand_id_previous,
                'hand_id_current': hand_id_current,
                'previous_total_zar': previous_total_zar,
                'current_total_zar': current_total_zar,
                'zar_delta': zar_delta,
                'direction': direction,
                'notes': notes,
                'metadata': metadata
            }

            _write_jsonl_fallback(ZAR_LEDGER_LOG, entry)
            return entry
        except Exception as e2:
            print(f'[AUDIT] ZAR ledger fallback failed: {e2}')
            return None


# ══════════════════════════════════════════════════════════════════════════════
# QUERY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_user_audit_logs(username=None, limit=100, offset=0):
    """Get user audit logs (login/logout)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if username:
            cursor.execute('''
                SELECT * FROM user_logs
                WHERE username = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            ''', (username, limit, offset))
        else:
            cursor.execute('''
                SELECT * FROM user_logs
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        print(f'[AUDIT] get_user_audit_logs failed: {e}')
        return []


def get_zar_ledger(username=None, limit=100, offset=0):
    """Get ZAR ledger entries"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if username:
            cursor.execute('''
                SELECT * FROM zar_ledger
                WHERE username = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            ''', (username, limit, offset))
        else:
            cursor.execute('''
                SELECT * FROM zar_ledger
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        print(f'[AUDIT] get_zar_ledger failed: {e}')
        return []


def get_zar_summary(username):
    """Get ZAR ledger summary for a user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                COUNT(*) as total_hands,
                SUM(CASE WHEN direction = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN direction = 'LOSS' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN direction = 'FLAT' THEN 1 ELSE 0 END) as flat,
                SUM(zar_delta) as net_zar,
                AVG(zar_delta) as avg_zar_per_hand,
                MAX(zar_delta) as biggest_win,
                MIN(zar_delta) as biggest_loss
            FROM zar_ledger
            WHERE username = ?
        ''', (username,))

        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None
    except Exception as e:
        print(f'[AUDIT] get_zar_summary failed: {e}')
        return None


# Initialize tables on import
init_audit_tables()
