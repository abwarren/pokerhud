"""
Equity Engine Routes for PLO Remote Control
Runs real equity calculations using eval7 and streams results
"""

import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from flask import jsonify, request, Response

# Global state for jobs
jobs_store = {}
jobs_lock = threading.Lock()

# Production engine paths
SCRIPTS_DIR = Path('/opt/plo-engine-backend/scripts')
ENGINE_PYTHON = '/opt/plo-engine-backend/venv/bin/python3'

# Variant configuration — script names match production (hyphenated)
VARIANT_CONFIG = {
    'plo4-6max': {'script': 'plo4-6max.py', 'cards_per_hand': 4, 'max_players': 6},
    'plo4-8max': {'script': 'plo4-8max.py', 'cards_per_hand': 4, 'max_players': 8},
    'plo4-9max': {'script': 'plo4-9max.py', 'cards_per_hand': 4, 'max_players': 9},
    'plo5-5max': {'script': 'plo5-5max.py', 'cards_per_hand': 5, 'max_players': 5},
    'plo5-6max': {'script': 'plo5-6max.py', 'cards_per_hand': 5, 'max_players': 6},
    'plo5-8max': {'script': 'plo5-8max.py', 'cards_per_hand': 5, 'max_players': 8},
    'plo5-9max': {'script': 'plo5-9max.py', 'cards_per_hand': 5, 'max_players': 9},
    'plo5-hu':   {'script': 'plo5-6max.py', 'cards_per_hand': 5, 'max_players': 2},
    'plo6-5max': {'script': 'plo6-5max.py', 'cards_per_hand': 6, 'max_players': 5},
    'plo6-6max': {'script': 'plo6-6max.py', 'cards_per_hand': 6, 'max_players': 6},
    'plo6-8max': {'script': 'plo6-8max.py', 'cards_per_hand': 6, 'max_players': 8},
    'plo7-5max': {'script': 'plo7-5max.py', 'cards_per_hand': 7, 'max_players': 5},
    'plo7-6max': {'script': 'plo7-6max.py', 'cards_per_hand': 7, 'max_players': 6},
}


def parse_hands_input(hands_text, variant=None):
    """Parse hands from collector format. Separates board from hands using variant info."""
    parsed_lines = [line.strip() for line in hands_text.strip().split(chr(10)) if line.strip()]

    hands = []
    board = None

    # Handle explicit BOARD: prefix from collector format
    for i, line in enumerate(parsed_lines):
        if line.upper().startswith('BOARD:'):
            board = line[6:].strip()
            parsed_lines = parsed_lines[:i] + parsed_lines[i+1:]
            break

    expected_hand_len = None
    if variant and variant in VARIANT_CONFIG:
        expected_hand_len = VARIANT_CONFIG[variant]['cards_per_hand'] * 2

    BOARD_LENGTHS = {6, 8, 10}

    for line in parsed_lines:
        line_len = len(line)
        if expected_hand_len:
            if line_len != expected_hand_len and line_len in BOARD_LENGTHS:
                board = line
            elif line_len == expected_hand_len:
                hands.append(line)
        else:
            hands.append(line)

    if not variant and len(hands) >= 3:
        lengths = [len(h) for h in hands]
        majority_len = max(set(lengths), key=lengths.count)
        last = hands[-1]
        if len(last) != majority_len and len(last) in BOARD_LENGTHS:
            board = hands.pop()

    return hands, board


def run_equity_job(job_id, variant, hands, board=None):
    """Run equity calculation using production engine in background thread"""

    with jobs_lock:
        jobs_store[job_id]['status'] = 'running'
        jobs_store[job_id]['started_at'] = time.time()

    config = VARIANT_CONFIG.get(variant)
    if not config:
        with jobs_lock:
            jobs_store[job_id]['status'] = 'error'
            jobs_store[job_id]['error'] = f'Unknown variant: {variant}'
        return

    script_path = SCRIPTS_DIR / config['script']
    if not script_path.exists():
        with jobs_lock:
            jobs_store[job_id]['status'] = 'error'
            jobs_store[job_id]['error'] = f'Script not found: {script_path}'
        return

    # Write hands to temp file (production engine reads from file)
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, dir='/tmp') as tf:
            for hand in hands:
                tf.write(hand + '\n')
            if board:
                tf.write(board + '\n')
            tmp_path = tf.name
    except Exception as e:
        with jobs_lock:
            jobs_store[job_id]['status'] = 'error'
            jobs_store[job_id]['error'] = f'Failed to write temp file: {e}'
        return

    cmd = [ENGINE_PYTHON, str(script_path), tmp_path]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, 'TERM': 'dumb', 'NO_COLOR': '1'},
        )

        output_lines = []

        for line in iter(process.stdout.readline, ''):
            if line:
                # Strip ANSI escape codes for clean output
                clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip('\n'))
                with jobs_lock:
                    jobs_store[job_id]['output'].append(clean)
                output_lines.append(clean)

        process.wait()

        results = parse_equity_results(output_lines, hands)

        with jobs_lock:
            jobs_store[job_id]['status'] = 'completed'
            jobs_store[job_id]['completed_at'] = time.time()
            jobs_store[job_id]['results'] = results
            jobs_store[job_id]['exit_code'] = process.returncode

    except Exception as e:
        with jobs_lock:
            jobs_store[job_id]['status'] = 'error'
            jobs_store[job_id]['error'] = str(e)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def parse_equity_results(output_lines, hands):
    """Parse equity results from production engine output.
    
    Looks for patterns in the ALL MATCHUPS table and per-pair equity bars.
    """
    results = {
        'matchups': [],
        'summary': {},
    }

    # Extract street, runtime, pairs from summary lines
    for line in output_lines:
        stripped = line.strip()
        if stripped.startswith('Street'):
            results['summary']['street'] = stripped.split()[-1] if stripped.split() else ''
        elif stripped.startswith('Total runtime'):
            results['summary']['runtime'] = stripped.split()[-1] if stripped.split() else ''
        elif stripped.startswith('Pairs evaluated'):
            results['summary']['pairs'] = stripped.split()[-1] if stripped.split() else ''

    # Parse per-pair equity bars: "53.0% vs  47.0%"
    # These appear in lines like: |    [####...]   53.0% vs  47.0%
    pair_re = re.compile(r'(\d+\.\d+)%\s+vs\s+(\d+\.\d+)%')
    
    # Parse ALL MATCHUPS table lines
    # Format: rank # underdog_hand (name) favourite_hand (name) UndRaw UndReal Disparity FavRaw FavReal
    matchup_re = re.compile(
        r'^\s*\d+\s+\d+\s+'          # rank and pair number
        r'(\S+)\s+\(\w+\)\s+'        # underdog hand (name)
        r'(\S+)\s+\(\w+\)\s+'        # favourite hand (name)
        r'([\d.]+)%\s+'              # underdog raw
        r'([\d.]+)%\s+'              # underdog realized
        r'([\d.]+)%\s+'              # disparity
        r'([\d.]+)%\s+'              # favourite raw
        r'([\d.]+)%'                 # favourite realized
    )

    in_matchups = False
    for line in output_lines:
        if 'ALL MATCHUPS' in line:
            in_matchups = True
            continue
        if in_matchups:
            m = matchup_re.match(line)
            if m:
                und_hand = m.group(1)
                fav_hand = m.group(2)
                und_raw = float(m.group(3)) / 100.0
                und_real = float(m.group(4)) / 100.0
                disparity = float(m.group(5)) / 100.0
                fav_raw = float(m.group(6)) / 100.0
                fav_real = float(m.group(7)) / 100.0
                results['matchups'].append({
                    'hand1': fav_hand,
                    'hand2': und_hand,
                    'eq1': fav_raw,
                    'eq2': und_raw,
                    'eq1_realized': fav_real,
                    'eq2_realized': und_real,
                    'disparity': disparity,
                    'samples': None,
                })

    # Fallback: parse simple "X% vs Y%" lines if ALL MATCHUPS table wasn't found
    if not results['matchups']:
        pair_idx = 0
        seen_raw = False
        for line in output_lines:
            m = pair_re.search(line)
            if m and 'RAW equity' not in line and 'REALIZED' not in line:
                eq1 = float(m.group(1)) / 100.0
                eq2 = float(m.group(2)) / 100.0
                if not seen_raw:
                    # First occurrence per pair is RAW
                    h1 = hands[min(pair_idx, len(hands)-1)] if pair_idx < len(hands) else f'Hand{pair_idx+1}'
                    h2 = hands[min(pair_idx+1, len(hands)-1)] if pair_idx+1 < len(hands) else f'Hand{pair_idx+2}'
                    results['matchups'].append({
                        'hand1': h1,
                        'hand2': h2,
                        'eq1': eq1,
                        'eq2': eq2,
                        'disparity': eq1 - eq2,
                        'samples': None,
                    })
                    seen_raw = True
                else:
                    seen_raw = False
                    pair_idx += 1

    return results


def register_equity_routes(app):
    """Register equity engine routes with Flask app"""

    @app.route("/api/run", methods=["POST"])
    def run_engine():
        """Start equity calculation job"""
        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': 'No payload'}), 400

        variant = data.get('variant', 'plo5-6max')
        hands_text = data.get('hands', '')

        if not hands_text:
            return jsonify({'ok': False, 'error': 'No hands provided'}), 400

        hands, board = parse_hands_input(hands_text, variant=variant)

        if len(hands) < 2:
            return jsonify({'ok': False, 'error': 'Need at least 2 hands'}), 400

        job_id = str(uuid.uuid4())[:8]

        with jobs_lock:
            jobs_store[job_id] = {
                'job_id': job_id,
                'variant': variant,
                'hands': hands,
                'board': board,
                'status': 'pending',
                'output': [],
                'results': None,
                'error': None,
                'created_at': time.time(),
                'started_at': None,
                'completed_at': None,
            }

        thread = threading.Thread(
            target=run_equity_job,
            args=(job_id, variant, hands, board),
            daemon=True
        )
        thread.start()

        return jsonify({
            'ok': True,
            'job_id': job_id,
            'variant': variant,
            'hands': hands,
            'board': board,
        })

    @app.route("/api/stream/<job_id>")
    def stream_job(job_id):
        """Stream job output via Server-Sent Events"""

        def generate():
            last_line = 0
            max_wait = 300
            start_time = time.time()

            while True:
                if time.time() - start_time > max_wait:
                    yield f"data: [TIMEOUT]\n\n"
                    break

                with jobs_lock:
                    job = jobs_store.get(job_id)
                    if not job:
                        yield f"data: [ERROR: Job not found]\n\n"
                        break

                    output = job['output']
                    if len(output) > last_line:
                        for line in output[last_line:]:
                            yield f"data: {line}\n\n"
                        last_line = len(output)

                    if job['status'] in ('completed', 'error'):
                        if job['status'] == 'error':
                            yield f"data: [ERROR: {job.get('error', 'Unknown error')}]\n\n"
                        yield "event: done\ndata: complete\n\n"
                        break

                time.sleep(0.5)

        return Response(generate(), mimetype='text/event-stream')

    @app.route("/api/results/<job_id>")
    def get_results(job_id):
        """Get parsed results for a job"""
        with jobs_lock:
            job = jobs_store.get(job_id)
            if not job:
                return jsonify({'ok': False, 'error': 'Job not found'}), 404

            if job['status'] != 'completed':
                return jsonify({
                    'ok': False,
                    'error': 'Job not completed',
                    'status': job['status']
                }), 400

            return jsonify({
                'ok': True,
                'job_id': job_id,
                'variant': job['variant'],
                'status': job['status'],
                'results': job['results'],
                'elapsed': job['completed_at'] - job['started_at'] if job['started_at'] else None,
            })

    @app.route("/api/validate", methods=["POST"])
    def validate_hands():
        """Validate hand input without running"""
        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': 'No payload'}), 400
        variant = data.get('variant', 'plo5-6max')
        hands_text = data.get('hands', '')
        hands, board = parse_hands_input(hands_text, variant=variant)
        return jsonify({
            'ok': True,
            'hands': hands,
            'board': board,
            'count': len(hands),
            'variant': variant,
        })

    @app.route("/api/jobs")
    def list_jobs():
        """List all jobs"""
        with jobs_lock:
            jobs_list = []
            for job in jobs_store.values():
                jobs_list.append({
                    'job_id': job['job_id'],
                    'variant': job['variant'],
                    'status': job['status'],
                    'created_at': job['created_at'],
                })
            jobs_list.sort(key=lambda j: j['created_at'], reverse=True)
        return jsonify({'ok': True, 'jobs': jobs_list})
