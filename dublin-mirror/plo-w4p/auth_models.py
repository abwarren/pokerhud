"""
Authentication and Database Models for PLO Remote Control
Additive auth layer - does not modify existing functionality
"""

import sqlite3
import hashlib
import secrets
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Database path
DB_PATH = '/opt/plo-w4p/database.db'

def get_db_connection():
    """Get SQLite database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Initialize database tables - idempotent"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'operator',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')

    # User activity logs table (admin only)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER,
            username TEXT,
            action TEXT NOT NULL,
            resource TEXT,
            status TEXT,
            ip_address TEXT,
            user_agent TEXT,
            details_json TEXT
        )
    ''')

    # Trading/action logs table (admin only)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trading_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER,
            username TEXT,
            table_id TEXT,
            seat_no INTEGER,
            action_type TEXT NOT NULL,
            action_value TEXT,
            result TEXT,
            error_message TEXT,
            snapshot_id TEXT,
            engine_context_id TEXT,
            metadata_json TEXT
        )
    ''')

    # Create default admin user if doesn't exist
    cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('admin',))
    if cursor.fetchone()[0] == 0:
        default_password = secrets.token_urlsafe(16)  # Generate random password
        password_hash = generate_password_hash(default_password, method='pbkdf2:sha256')
        cursor.execute(
            'INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)',
            ('admin', 'admin@plo-remote.local', password_hash, 'admin')
        )
        conn.commit()
        print(f'\n[AUTH] Default admin user created')
        print(f'[AUTH] Username: admin')
        print(f'[AUTH] Password: {default_password}')
        print(f'[AUTH] IMPORTANT: Change this password immediately after first login!\n')

    conn.commit()
    conn.close()

class User(UserMixin):
    """User model for Flask-Login"""

    def __init__(self, id, username, email, role, is_active):
        self.id = id
        self.username = username
        self.email = email
        self.role = role
        self._is_active = bool(is_active)
    
    @property
    def is_active(self):
        """Override Flask-Login's is_active property"""
        return self._is_active

    def is_admin(self):
        """Check if user has admin role"""
        return self.role == 'admin'

    @staticmethod
    def get(user_id):
        """Get user by ID"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return User(
                id=row['id'],
                username=row['username'],
                email=row['email'],
                role=row['role'],
                is_active=row['is_active']
            )
        return None

    @staticmethod
    def get_by_username(username):
        """Get user by username"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return User(
                id=row['id'],
                username=row['username'],
                email=row['email'],
                role=row['role'],
                is_active=row['is_active']
            ), row['password_hash']
        return None, None

    @staticmethod
    def authenticate(username, password):
        """Authenticate user"""
        user, password_hash = User.get_by_username(username)
        if user and check_password_hash(password_hash, password):
            # Update last login
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE users SET last_login = ? WHERE id = ?',
                (datetime.now(), user.id)
            )
            conn.commit()
            conn.close()
            return user
        return None

def log_user_activity(user_id, username, action, resource=None, status='success',
                      ip_address=None, user_agent=None, details=None):
    """Log user activity (admin viewable only)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_logs
        (user_id, username, action, resource, status, ip_address, user_agent, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, action, resource, status, ip_address, user_agent, details))
    conn.commit()
    conn.close()

def log_trading_action(user_id, username, table_id, seat_no, action_type,
                       action_value=None, result='pending', error_message=None,
                       snapshot_id=None, engine_context_id=None, metadata=None):
    """Log trading/action event (admin viewable only)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trading_logs
        (user_id, username, table_id, seat_no, action_type, action_value,
         result, error_message, snapshot_id, engine_context_id, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, table_id, seat_no, action_type, action_value,
          result, error_message, snapshot_id, engine_context_id, metadata))
    conn.commit()
    conn.close()
