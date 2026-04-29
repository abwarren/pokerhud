"""
BLM — Basketball League Manager API Routes
Register with: register_blm_routes(app)
"""

from flask import request, jsonify
import blm_database as blm_db


def register_blm_routes(app):

    @app.route('/api/blm/init', methods=['POST'])
    def blm_init():
        blm_db.init_db()
        return jsonify({'status': 'ok', 'message': 'BLM database initialized'})

    # ── Games ────────────────────────────────────────────────────

    @app.route('/api/blm/games', methods=['GET'])
    def blm_games():
        status = request.args.get('status')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        games = blm_db.get_games(status=status, limit=limit, offset=offset)
        return jsonify({'status': 'ok', 'count': len(games), 'games': games})

    @app.route('/api/blm/games', methods=['POST'])
    def blm_add_game():
        data = request.get_json(force=True)
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON body'}), 400
        required = ['game_id', 'home_team', 'away_team']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({'status': 'error', 'message': f'Missing fields: {missing}'}), 400
        result = blm_db.add_game(data)
        return jsonify(result)

    @app.route('/api/blm/games/batch', methods=['POST'])
    def blm_add_games_batch():
        data = request.get_json(force=True)
        if not isinstance(data, list):
            return jsonify({'status': 'error', 'message': 'Expected JSON array'}), 400
        results = []
        for game in data:
            try:
                r = blm_db.add_game(game)
                results.append(r)
            except Exception as e:
                results.append({'status': 'error', 'game_id': game.get('game_id'), 'message': str(e)})
        ok = sum(1 for r in results if r.get('status') == 'ok')
        return jsonify({'status': 'ok', 'added': ok, 'errors': len(results) - ok, 'results': results})

    @app.route('/api/blm/games/<game_id>', methods=['GET'])
    def blm_get_game(game_id):
        game = blm_db.get_game(game_id)
        if not game:
            return jsonify({'status': 'error', 'message': 'Game not found'}), 404
        bets = blm_db.get_bets(game_id=game_id)
        game['bets'] = bets
        return jsonify({'status': 'ok', 'game': game})

    # ── Bets ─────────────────────────────────────────────────────

    @app.route('/api/blm/bets', methods=['GET'])
    def blm_bets():
        game_id = request.args.get('game_id')
        result = request.args.get('result')
        limit = int(request.args.get('limit', 200))
        bets = blm_db.get_bets(game_id=game_id, result=result, limit=limit)
        return jsonify({'status': 'ok', 'count': len(bets), 'bets': bets})

    @app.route('/api/blm/bets', methods=['POST'])
    def blm_add_bet():
        data = request.get_json(force=True)
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON body'}), 400
        if 'market_line' not in data or 'game_id' not in data:
            return jsonify({'status': 'error', 'message': 'game_id and market_line required'}), 400
        result = blm_db.add_bet(data)
        return jsonify(result)

    @app.route('/api/blm/bets/batch', methods=['POST'])
    def blm_add_bets_batch():
        data = request.get_json(force=True)
        if not isinstance(data, list):
            return jsonify({'status': 'error', 'message': 'Expected JSON array'}), 400
        results = []
        for bet in data:
            try:
                r = blm_db.add_bet(bet)
                results.append(r)
            except Exception as e:
                results.append({'status': 'error', 'message': str(e)})
        ok = sum(1 for r in results if r.get('status') == 'ok')
        return jsonify({'status': 'ok', 'added': ok, 'errors': len(results) - ok, 'results': results})

    @app.route('/api/blm/bets/<int:bet_id>/settle', methods=['POST'])
    def blm_settle_bet(bet_id):
        data = request.get_json(force=True)
        blm_db.settle_bet(bet_id, data['result'], data.get('final_total'), data.get('profit'))
        return jsonify({'status': 'ok', 'bet_id': bet_id})

    @app.route('/api/blm/settle', methods=['POST'])
    def blm_auto_settle():
        count = blm_db.auto_settle_bets()
        return jsonify({'status': 'ok', 'settled': count})

    # ── Stats ────────────────────────────────────────────────────

    @app.route('/api/blm/stats', methods=['GET'])
    def blm_stats():
        stats = blm_db.get_stats()
        return jsonify({'status': 'ok', **stats})

    # ── Health ───────────────────────────────────────────────────

    @app.route('/api/blm/health', methods=['GET'])
    def blm_health():
        try:
            db = blm_db.get_db()
            games = db.execute("SELECT COUNT(*) FROM games").fetchone()[0]
            bets = db.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
            db.close()
            return jsonify({'status': 'ok', 'games': games, 'bets': bets})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
