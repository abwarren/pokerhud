import os
from functools import wraps
from flask import session, redirect, url_for, request, jsonify

# Auth configuration
AUTH_MODE = os.getenv('AUTH_MODE', 'dev_bypass')  # normal | dev_bypass | disabled
NODE_ENV = os.getenv('NODE_ENV', 'development')  # production | staging | development

# Public routes (always accessible)
PUBLIC_ROUTES = [
    '/',
    '/api/health',
    '/api/table/latest',
    '/api/tables',
    '/api/table/<table_id>',
    '/aggregate',
    '/collector',
    '/engine',
    '/n4p.js',
    '/n4p-tampermonkey.user.js'
]

# Protected routes (require auth in production)
PROTECTED_ROUTES = [
    '/admin/*',
    '/api/commands/queue',
    '/api/bots/deploy-seating',
    '/api/aggregate/snapshot'
]

def get_dev_user():
    """Return dev user for bypass mode"""
    return {
        'id': 'dev-user',
        'username': 'dev',
        'role': 'admin'
    }

def is_route_public(route):
    """Check if route is public"""
    for public_route in PUBLIC_ROUTES:
        if route == public_route or route.startswith(public_route.replace('<', '').replace('>', '')):
            return True
    return False

def require_auth(f):
    """Auth decorator with environment-aware bypass"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Production safety check
        if NODE_ENV == 'production' and AUTH_MODE == 'dev_bypass':
            return jsonify({
                'ok': False,
                'error': 'dev_bypass is forbidden in production'
            }), 403
        
        # Check if route is public
        if is_route_public(request.path):
            return f(*args, **kwargs)
        
        # Dev bypass mode (staging/development only)
        if AUTH_MODE == 'dev_bypass' and NODE_ENV != 'production':
            session['user'] = get_dev_user()
            return f(*args, **kwargs)
        
        # Disabled mode (complete bypass - use with caution)
        if AUTH_MODE == 'disabled':
            session['user'] = get_dev_user()
            return f(*args, **kwargs)
        
        # Normal auth mode
        if 'user' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'error': 'Authentication required'}), 401
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    
    return decorated_function

def init_auth_config():
    """Print auth configuration on startup"""
    print(f"[AUTH] Mode: {AUTH_MODE}")
    print(f"[AUTH] Environment: {NODE_ENV}")
    print(f"[AUTH] Public routes: {len(PUBLIC_ROUTES)}")
    
    if NODE_ENV == 'production' and AUTH_MODE != 'normal':
        print("[AUTH] ⚠️  WARNING: Non-normal auth mode in production!")
