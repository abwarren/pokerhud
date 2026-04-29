"""
Flask API for PLO Remote Control
Generated from AppDNA model
Integrates with existing app.py or runs standalone
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import database as db
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Enable CORS for Cape Town frontend

# Initialize database on startup
db.init_database()

# ============================================================================
# PLAYER ENDPOINTS (from PlayerStats report)
# ============================================================================

@app.route('/api/players', methods=['GET'])
def get_players():
    """Get all players with status"""
    try:
        players = db.get_all_players()
        return jsonify(players), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/players/<int:player_id>', methods=['GET'])
def get_player(player_id):
    """Get specific player"""
    try:
        player = db.get_player_by_id(player_id)
        if player:
            return jsonify(player), 200
        return jsonify({"error": "Player not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/players/<int:player_id>', methods=['PUT'])
def update_player(player_id):
    """Update player (from PlayerEdit form)"""
    try:
        data = request.json
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE players
                SET username = ?, password = ?, eip = ?, eni = ?, container_name = ?
                WHERE player_id = ?
            ''', (
                data.get('username'),
                data.get('password'),
                data.get('eip'),
                data.get('eni'),
                data.get('containerName'),
                player_id
            ))
            conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/players/summary', methods=['GET'])
def get_players_summary():
    """Get player summary statistics"""
    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'IDLE' THEN 1 ELSE 0 END) as idle,
                    SUM(CASE WHEN status = 'SEATED' THEN 1 ELSE 0 END) as seated,
                    SUM(CASE WHEN status = 'PLAYING' THEN 1 ELSE 0 END) as playing,
                    SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) as error
                FROM players
            ''')
            row = cursor.fetchone()
            return jsonify(dict(row)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# TABLE ENDPOINTS (from TableView form)
# ============================================================================

@app.route('/api/table/latest', methods=['GET'])
def get_table_latest():
    """Get latest table state with seats"""
    try:
        table = db.get_table_latest()
        if not table:
            return jsonify({"error": "No table found"}), 404

        seats = db.get_seats_by_table(table['table_id'])

        # Parse JSON fields
        if table.get('board'):
            table['board'] = json.loads(table['board']) if isinstance(table['board'], str) else table['board']

        for seat in seats:
            if seat.get('hole_cards'):
                seat['hole_cards'] = json.loads(seat['hole_cards']) if isinstance(seat['hole_cards'], str) else seat['hole_cards']

        return jsonify({
            "table": table,
            "seats": seats
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/table/update', methods=['POST'])
def update_table():
    """Update table state (called by bot scrapers)"""
    try:
        data = request.json
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE tables
                SET pot = ?, board = ?, dealer_seat = ?, current_street = ?, last_update = CURRENT_TIMESTAMP
                WHERE table_id = 1
            ''', (
                data.get('pot', 0),
                json.dumps(data.get('board', [])),
                data.get('dealerSeat'),
                data.get('currentStreet')
            ))
            conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/seats/<int:seat_id>', methods=['PUT'])
def update_seat(seat_id):
    """Update seat data"""
    try:
        data = request.json
        db.update_seat(
            seat_id,
            player_id=data.get('playerId'),
            player_name=data.get('playerName'),
            stack=data.get('stack'),
            hole_cards=json.dumps(data.get('holeCards', [])) if data.get('holeCards') else None,
            is_active=data.get('isActive', False)
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# ACTION ENDPOINTS (from SendAction workflow)
# ============================================================================

@app.route('/api/commands/queue', methods=['POST'])
def queue_command():
    """Queue action command for player"""
    try:
        data = request.json
        player_id = data.get('player_id')
        action_type = data.get('action_type')
        amount = data.get('amount')

        # Validate action type
        valid_actions = ['FOLD', 'CHECK', 'CALL', 'RAISE', 'CASHOUT']
        if action_type not in valid_actions:
            return jsonify({"error": f"Invalid action type. Must be one of {valid_actions}"}), 400

        action_id = db.queue_action(player_id, action_type, amount)
        return jsonify({
            "success": True,
            "action_id": action_id,
            "message": f"{action_type} queued for player {player_id}"
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/commands/pending', methods=['GET'])
def get_pending_commands():
    """Get pending commands (polled by bot containers)"""
    try:
        player_name = request.args.get('player_name')
        actions = db.get_pending_actions()

        if player_name:
            actions = [a for a in actions if a['player_name'] == player_name]

        return jsonify(actions), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/commands/ack', methods=['POST'])
def acknowledge_command():
    """Acknowledge command received"""
    try:
        data = request.json
        action_id = data.get('action_id')
        db.acknowledge_action(action_id)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/commands/complete', methods=['POST'])
def complete_command():
    """Mark command as executed"""
    try:
        data = request.json
        action_id = data.get('action_id')
        db.complete_action(action_id)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# HAND HISTORY ENDPOINTS (from HandHistory report)
# ============================================================================

@app.route('/api/hands', methods=['GET'])
def get_hands():
    """Get hand history"""
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        hands = db.get_hands(limit, offset)

        # Parse JSON fields
        for hand in hands:
            if hand.get('board'):
                hand['board'] = json.loads(hand['board']) if isinstance(hand['board'], str) else hand['board']
            if hand.get('winners'):
                hand['winners'] = json.loads(hand['winners']) if isinstance(hand['winners'], str) else hand['winners']

        return jsonify(hands), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/hands', methods=['POST'])
def save_hand():
    """Save completed hand"""
    try:
        data = request.json
        hand_id = db.save_hand(
            table_id=data.get('table_id', 1),
            hand_number=data['hand_number'],
            board=data['board'],
            pot=data['pot'],
            winners=data.get('winners', []),
            raw_text=data['raw_text']
        )
        return jsonify({"success": True, "hand_id": hand_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# DEPLOYMENT ENDPOINTS (from DeploymentForm and DeployBot workflow)
# ============================================================================

@app.route('/api/bot/deploy', methods=['POST'])
def deploy_bots():
    """Deploy bots to table"""
    try:
        data = request.json
        bot_count = data.get('bot_count')
        mode = data.get('mode', 'SEATING_ONLY')
        buy_in_mode = data.get('buy_in_mode', 'MIN')

        # Create deployment record
        deployment_id = db.create_deployment(bot_count, mode, buy_in_mode)

        # TODO: Trigger actual bot deployment
        # This would call your existing bot_deployment.py logic

        return jsonify({
            "success": True,
            "deployment_id": deployment_id,
            "message": f"Deploying {bot_count} bots in {mode} mode"
        }), 202
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/deployments', methods=['GET'])
def get_deployments():
    """Get deployment history (from DeploymentLog report)"""
    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM deployments
                ORDER BY created_date DESC
                LIMIT 25
            ''')
            deployments = [dict(row) for row in cursor.fetchall()]
        return jsonify(deployments), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/deployments/<int:deployment_id>', methods=['GET'])
def get_deployment(deployment_id):
    """Get specific deployment"""
    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM deployments WHERE deployment_id = ?', (deployment_id,))
            row = cursor.fetchone()
            if row:
                return jsonify(dict(row)), 200
            return jsonify({"error": "Deployment not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/deployments/<int:deployment_id>', methods=['PUT'])
def update_deployment_status(deployment_id):
    """Update deployment status"""
    try:
        data = request.json
        db.update_deployment(
            deployment_id,
            status=data.get('status'),
            success_count=data.get('success_count'),
            failed_count=data.get('failed_count'),
            logs=data.get('logs')
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# HEALTH & STATUS
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "database": "connected"
    }), 200

@app.route('/api/snapshot', methods=['GET'])
def get_snapshot():
    """Get complete system snapshot"""
    try:
        table = db.get_table_latest()
        seats = db.get_seats_by_table(1)
        players = db.get_all_players()
        pending_actions = db.get_pending_actions()

        return jsonify({
            "table": table,
            "seats": seats,
            "players": players,
            "pending_actions": pending_actions,
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == '__main__':
    print("🚀 PLO Remote Control API Starting...")
    print("📊 Database:", db.DB_PATH)
    print("🌐 Server: http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
