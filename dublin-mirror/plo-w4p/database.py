"""
Database layer for PLO Remote Control
Generated from AppDNA model - SQLite implementation
"""

import sqlite3
from datetime import datetime
from contextlib import contextmanager
import json

DB_PATH = "/opt/plo-w4p/plo.db"

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """Initialize all tables from AppDNA model"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Players table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                player_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                eip TEXT NOT NULL,
                eni TEXT NOT NULL,
                container_name TEXT NOT NULL,
                status TEXT DEFAULT 'IDLE',
                seat_number INTEGER,
                stack REAL,
                last_heartbeat DATETIME,
                created_date DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tables table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tables (
                table_id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                game_type TEXT DEFAULT 'PLO',
                stakes TEXT DEFAULT '1/2 ZAR',
                pot REAL DEFAULT 0,
                board TEXT,
                dealer_seat INTEGER,
                current_street TEXT,
                last_update DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Seats table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seats (
                seat_id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                seat_number INTEGER NOT NULL,
                player_id INTEGER,
                player_name TEXT,
                stack REAL,
                hole_cards TEXT,
                is_active BOOLEAN DEFAULT 0,
                has_acted BOOLEAN DEFAULT 0,
                FOREIGN KEY (table_id) REFERENCES tables(table_id),
                FOREIGN KEY (player_id) REFERENCES players(player_id)
            )
        ''')

        # Actions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS actions (
                action_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                amount REAL,
                status TEXT DEFAULT 'PENDING',
                created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                executed_date DATETIME,
                FOREIGN KEY (player_id) REFERENCES players(player_id)
            )
        ''')

        # Hands table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hands (
                hand_id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                hand_number TEXT UNIQUE NOT NULL,
                board TEXT NOT NULL,
                pot REAL NOT NULL,
                winners TEXT,
                raw_text TEXT NOT NULL,
                created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (table_id) REFERENCES tables(table_id)
            )
        ''')

        # Deployments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deployments (
                deployment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_count INTEGER NOT NULL,
                mode TEXT NOT NULL,
                buy_in_mode TEXT NOT NULL,
                status TEXT DEFAULT 'STARTED',
                success_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                logs TEXT,
                created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_date DATETIME
            )
        ''')

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_status ON players(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_actions_player ON actions(player_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_hands_date ON hands(created_date)')

        # Insert default table if needed
        cursor.execute('SELECT COUNT(*) FROM tables')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO tables (table_name, game_type, stakes)
                VALUES ('Main Table', 'PLO', '1/2 ZAR')
            ''')
            table_id = cursor.lastrowid

            # Create 9 empty seats
            for i in range(9):
                cursor.execute('''
                    INSERT INTO seats (table_id, seat_number, is_active)
                    VALUES (?, ?, 0)
                ''', (table_id, i))

        conn.commit()

    print(f"✅ Database initialized at {DB_PATH}")

# Helper functions for common queries

def get_all_players():
    """Get all players"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM players ORDER BY player_name')
        return [dict(row) for row in cursor.fetchall()]

def get_player_by_id(player_id):
    """Get player by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM players WHERE player_id = ?', (player_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_player_status(player_id, status, seat_number=None):
    """Update player status"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE players
            SET status = ?, seat_number = ?, last_heartbeat = CURRENT_TIMESTAMP
            WHERE player_id = ?
        ''', (status, seat_number, player_id))
        conn.commit()

def get_table_latest():
    """Get latest table state"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tables WHERE table_id = 1')
        row = cursor.fetchone()
        return dict(row) if row else None

def get_seats_by_table(table_id=1):
    """Get all seats for a table"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM seats WHERE table_id = ? ORDER BY seat_number', (table_id,))
        return [dict(row) for row in cursor.fetchall()]

def update_seat(seat_id, player_id=None, player_name=None, stack=None, hole_cards=None, is_active=False):
    """Update seat data"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE seats
            SET player_id = ?, player_name = ?, stack = ?, hole_cards = ?, is_active = ?
            WHERE seat_id = ?
        ''', (player_id, player_name, stack, hole_cards, is_active, seat_id))
        conn.commit()

def queue_action(player_id, action_type, amount=None):
    """Queue an action for a player"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO actions (player_id, action_type, amount, status)
            VALUES (?, ?, ?, 'PENDING')
        ''', (player_id, action_type, amount))
        conn.commit()
        return cursor.lastrowid

def get_pending_actions():
    """Get all pending actions"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT a.*, p.player_name, p.container_name
            FROM actions a
            JOIN players p ON a.player_id = p.player_id
            WHERE a.status = 'PENDING'
            ORDER BY a.created_date
        ''')
        return [dict(row) for row in cursor.fetchall()]

def acknowledge_action(action_id):
    """Mark action as acknowledged"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE actions
            SET status = 'ACKNOWLEDGED'
            WHERE action_id = ?
        ''', (action_id,))
        conn.commit()

def complete_action(action_id):
    """Mark action as executed"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE actions
            SET status = 'EXECUTED', executed_date = CURRENT_TIMESTAMP
            WHERE action_id = ?
        ''', (action_id,))
        conn.commit()

def save_hand(table_id, hand_number, board, pot, winners, raw_text):
    """Save completed hand"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO hands (table_id, hand_number, board, pot, winners, raw_text)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (table_id, hand_number, json.dumps(board), pot, json.dumps(winners), raw_text))
        conn.commit()
        return cursor.lastrowid

def get_hands(limit=50, offset=0):
    """Get hand history"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM hands
            ORDER BY created_date DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        return [dict(row) for row in cursor.fetchall()]

def create_deployment(bot_count, mode, buy_in_mode):
    """Create deployment record"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO deployments (bot_count, mode, buy_in_mode, status)
            VALUES (?, ?, ?, 'STARTED')
        ''', (bot_count, mode, buy_in_mode))
        conn.commit()
        return cursor.lastrowid

def update_deployment(deployment_id, status=None, success_count=None, failed_count=None, logs=None):
    """Update deployment record"""
    with get_db() as conn:
        cursor = conn.cursor()
        updates = []
        params = []

        if status:
            updates.append('status = ?')
            params.append(status)
        if success_count is not None:
            updates.append('success_count = ?')
            params.append(success_count)
        if failed_count is not None:
            updates.append('failed_count = ?')
            params.append(failed_count)
        if logs:
            updates.append('logs = ?')
            params.append(logs)

        if status in ['COMPLETED', 'FAILED']:
            updates.append('completed_date = CURRENT_TIMESTAMP')

        params.append(deployment_id)

        cursor.execute(f'''
            UPDATE deployments
            SET {', '.join(updates)}
            WHERE deployment_id = ?
        ''', params)
        conn.commit()

if __name__ == '__main__':
    init_database()
