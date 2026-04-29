"""
GoldRush API Endpoints - Add to app.py

These endpoints provide complete separation from PokerBet:
- Separate collector directory
- Separate table state
- Separate database queries (filtered by platform='GoldRush')
"""

from pathlib import Path

# Add to globals section
_GOLDRUSH_COLLECTOR_DIR = Path("/opt/plo-w4p/collectors/goldrush")
_GOLDRUSH_COLLECTOR_DIR.mkdir(parents=True, exist_ok=True)

# ── GoldRush Collector Endpoints ──────────────────────────────────────────────

@app.route('/api/goldrush/collector/save', methods=['POST'])
def goldrush_collector_save():
    """Save GoldRush collector data (completely separate from PokerBet)."""
    try:
        data = request.get_json()
        if not data or 'raw_batch' not in data:
            return jsonify({'ok': False, 'error': 'Missing raw_batch'}), 400

        raw_batch = data['raw_batch'].strip()
        if not raw_batch:
            return jsonify({'ok': False, 'error': 'Empty raw_batch'}), 400

        # Save to GoldRush-specific directory
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        file_path = _GOLDRUSH_COLLECTOR_DIR / f"collector_{ts}.txt"
        file_path.write_text(raw_batch, encoding='utf-8')

        app.logger.info(f'[GOLDRUSH-COLLECTOR] Saved: {file_path.name} ({len(raw_batch)} bytes)')
        return jsonify({'ok': True, 'file': file_path.name})

    except Exception as e:
        app.logger.error(f'[GOLDRUSH-COLLECTOR] Error: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/goldrush/collector/latest', methods=['GET'])
def goldrush_collector_latest():
    """Get latest GoldRush collector batch."""
    try:
        candidates = list(_GOLDRUSH_COLLECTOR_DIR.glob('*.txt'))
        if not candidates:
            return jsonify({'ok': False, 'error': 'No GoldRush collector data'}), 404

        latest = max(candidates, key=lambda f: f.stat().st_mtime)
        raw_batch = latest.read_text(encoding='utf-8').strip()

        return jsonify({
            'ok': True,
            'raw_batch': raw_batch,
            'file': latest.name,
            'timestamp': latest.stat().st_mtime,
            'platform': 'GoldRush'
        })

    except Exception as e:
        app.logger.error(f'[GOLDRUSH-COLLECTOR] Error fetching latest: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── GoldRush Table Endpoints ──────────────────────────────────────────────────

@app.route('/api/goldrush/tables', methods=['GET'])
def goldrush_list_tables():
    """List all GoldRush tables from database (filtered by platform)."""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, table_name, game_type, seats_total, 
                   small_blind, big_blind, stakes_display, 
                   is_active, platform, last_seen
            FROM poker_tables
            WHERE platform = 'GoldRush'
            ORDER BY stakes_display, table_name
        """)

        tables = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify({
            'ok': True,
            'platform': 'GoldRush',
            'count': len(tables),
            'tables': tables
        })

    except Exception as e:
        app.logger.error(f'[GOLDRUSH-API] Error listing tables: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/goldrush/table/<int:table_id>', methods=['GET'])
def goldrush_get_table(table_id):
    """Get specific GoldRush table info."""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM poker_tables
            WHERE id = ? AND platform = 'GoldRush'
        """, (table_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'ok': False, 'error': 'Table not found or not GoldRush'}), 404

        return jsonify({
            'ok': True,
            'platform': 'GoldRush',
            'table': dict(row)
        })

    except Exception as e:
        app.logger.error(f'[GOLDRUSH-API] Error fetching table: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


def _get_latest_goldrush_collector_batch():
    """Helper: Get latest GoldRush collector batch."""
    try:
        candidates = list(_GOLDRUSH_COLLECTOR_DIR.glob('*.txt'))
        if not candidates:
            return None
        latest = max(candidates, key=lambda f: f.stat().st_mtime)
        return latest.read_text(encoding='utf-8').strip()
    except Exception as e:
        app.logger.warning(f'[GOLDRUSH-COLLECTOR] Could not read batch: {e}')
        return None


# Note: GoldRush will have separate table state management if needed
# For now, collector data is the primary interface
