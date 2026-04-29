# Auth API Routes - Add these to app.py
# IAM-style authentication with role-based access control

from flask import request, jsonify, session, redirect, url_for
from flask_login import login_user, logout_user, current_user, login_required
from auth_models import User, log_user_activity, get_db_connection
from werkzeug.security import generate_password_hash
from datetime import datetime

# ── Auth API Routes ────────────────────────────────────────────────────────────

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """Login endpoint"""
    data = request.get_json()
    if not data:
        return jsonify({'ok': False, 'error': 'No data provided'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')
    remember = data.get('remember', False)

    if not username or not password:
        return jsonify({'ok': False, 'error': 'Username and password required'}), 400

    # Authenticate
    user = User.authenticate(username, password)

    if not user:
        # Log failed login attempt
        log_user_activity(
            user_id=None,
            username=username,
            action='login_failed',
            status='failure',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        return jsonify({'ok': False, 'error': 'Invalid credentials'}), 401

    if not user.is_active:
        log_user_activity(
            user_id=user.id,
            username=user.username,
            action='login_denied_inactive',
            status='failure',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        return jsonify({'ok': False, 'error': 'Account inactive'}), 403

    # Login successful
    login_user(user, remember=remember)

    log_user_activity(
        user_id=user.id,
        username=user.username,
        action='login_success',
        status='success',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )

    # Check if password change required
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT must_change_password FROM users WHERE id = ?', (user.id,))
    must_change = cursor.fetchone()[0]
    conn.close()

    response = {
        'ok': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'role': user.role
        },
        'must_change_password': bool(must_change),
        'redirect': '/change-password' if must_change else '/shell'
    }

    return jsonify(response), 200


@app.route('/api/auth/logout', methods=['POST'])
@login_required
def api_logout():
    """Logout endpoint"""
    log_user_activity(
        user_id=current_user.id,
        username=current_user.username,
        action='logout',
        status='success',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )

    logout_user()
    return jsonify({'ok': True}), 200


@app.route('/api/auth/me', methods=['GET'])
@login_required
def api_me():
    """Get current user info"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT must_change_password FROM users WHERE id = ?', (current_user.id,))
    must_change = cursor.fetchone()[0]
    conn.close()

    return jsonify({
        'ok': True,
        'user': {
            'id': current_user.id,
            'username': current_user.username,
            'role': current_user.role,
            'must_change_password': bool(must_change)
        }
    }), 200


@app.route('/api/auth/change-password', methods=['POST'])
@login_required
def api_change_password():
    """Change password endpoint"""
    data = request.get_json()
    if not data:
        return jsonify({'ok': False, 'error': 'No data provided'}), 400

    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'ok': False, 'error': 'Current and new password required'}), 400

    if len(new_password) < 4:
        return jsonify({'ok': False, 'error': 'New password must be at least 4 characters'}), 400

    # Verify current password
    user, password_hash = User.get_by_username(current_user.username)
    from werkzeug.security import check_password_hash

    if not check_password_hash(password_hash, current_password):
        log_user_activity(
            user_id=current_user.id,
            username=current_user.username,
            action='password_change_failed',
            status='failure',
            ip_address=request.remote_addr,
            details='incorrect current password'
        )
        return jsonify({'ok': False, 'error': 'Current password incorrect'}), 401

    # Update password
    new_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users
        SET password_hash = ?, must_change_password = 0, updated_at = ?
        WHERE id = ?
    ''', (new_hash, datetime.now(), current_user.id))
    conn.commit()
    conn.close()

    log_user_activity(
        user_id=current_user.id,
        username=current_user.username,
        action='password_changed',
        status='success',
        ip_address=request.remote_addr
    )

    return jsonify({'ok': True, 'message': 'Password changed successfully'}), 200
