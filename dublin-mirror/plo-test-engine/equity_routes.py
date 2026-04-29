"""
Equity Engine Routes for PLO Remote Control
Runs equity calculations and streams results
"""

import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from flask import jsonify, request, Response

# Global state for jobs
jobs_store = {}
jobs_lock = threading.Lock()

# Variant configuration
VARIANT_CONFIG = {
    'plo4-6max': {'script': 'plo4_6max.py', 'cards_per_hand': 4, 'max_players': 6},
    'plo4-8max': {'script': 'plo4_8max.py', 'cards_per_hand': 4, 'max_players': 8},
    'plo4-9max': {'script': 'plo4_9max.py', 'cards_per_hand': 4, 'max_players': 9},
    'plo5-5max': {'script': 'plo5_5max.py', 'cards_per_hand': 5, 'max_players': 5},
    'plo5-6max': {'script': 'plo5_6max.py', 'cards_per_hand': 5, 'max_players': 6},
    'plo5-8max': {'script': 'plo5_8max.py', 'cards_per_hand': 5, 'max_players': 8},
    'plo5-9max': {'script': 'plo5_9max.py', 'cards_per_hand': 5, 'max_players': 9},
    'plo5-hu':   {'script': 'plo5_hu.py',   'cards_per_hand': 5, 'max_players': 2},
    'plo6-5max': {'script': 'plo6_5max.py', 'cards_per_hand': 6, 'max_players': 5},
    'plo6-6max': {'script': 'plo6_6max.py', 'cards_per_hand': 6, 'max_players': 6},
    'plo6-8max': {'script': 'plo6_8max.py', 'cards_per_hand': 6, 'max_players': 8},
    'plo7-5max': {'script': 'plo7_5max.py', 'cards_per_hand': 7, 'max_players': 5},
    'plo7-6max': {'script': 'plo7_6max.py', 'cards_per_hand': 7, 'max_players': 6},
}

SCRIPTS_DIR = Path('/opt/plo-test/engine/scripts')


def parse_hands_input(hands_text):
    """Parse hands from collector format (e.g., 'AsKhQdJcTs\n9h9d8h8d7h')"""
    lines = [line.strip() for line in hands_text.strip().split('\n') if line.strip()]
    hands = []
    board = None

    for line in lines:
        # Board is typically longer (flop+turn+river = 15+ chars for full board)
        # PLO5 hands are 10 chars (5 cards * 2 chars each)
        # Flop(6) + Turn(2) + River(2) = 10 chars minimum for board
        # To distinguish, only treat as board if it's significantly longer than a hand
        if len(line) >= 15:
            board = line
        else:
            hands.append(line)

    return hands, board


def run_equity_job(job_id, variant, hands, board=None):
    """Run equity calculation in background thread"""

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

    # Build command
    cmd = ['python3', str(script_path)]

    # Add hands as arguments
    for hand in hands:
        cmd.append(hand)

    # Add board if provided
    if board:
        cmd.extend(['--board', board])

    try:
        # Run process and capture output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        output_lines = []

        # Stream output line by line
        for line in iter(process.stdout.readline, ''):
            if line:
                line = line.rstrip('\n')
                with jobs_lock:
                    jobs_store[job_id]['output'].append(line)
                output_lines.append(line)

        process.wait()

        # Parse results
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


def parse_equity_results(output_lines, hands):
    """Parse equity results from engine output"""
    results = {
        'matchups': [],
        'summary': {},
    }

    # Simple parser - look for equity percentages in output
    # Format: "Hand1 vs Hand2: 45.2% vs 54.8%"

    for line in output_lines:
        # Look for patterns like "AsKhQdJc vs TsTh9h9d"
        if ' vs ' in line and '%' in line:
            parts = line.split(':')
            if len(parts) == 2:
                hands_part = parts[0].strip()
                eq_part = parts[1].strip()

                hand_names = [h.strip() for h in hands_part.split(' vs ')]
                eq_values = [e.strip().replace('%', '') for e in eq_part.split(' vs ')]

                if len(hand_names) == 2 and len(eq_values) == 2:
                    try:
                        eq1 = float(eq_values[0]) / 100.0
                        eq2 = float(eq_values[1]) / 100.0
                        disparity = eq1 - eq2

                        results['matchups'].append({
                            'hand1': hand_names[0],
                            'hand2': hand_names[1],
                            'eq1': eq1,
                            'eq2': eq2,
                            'disparity': disparity,
                            'samples': None,
                        })
                    except ValueError:
                        pass

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

        # Parse hands
        hands, board = parse_hands_input(hands_text)

        if len(hands) < 2:
            return jsonify({'ok': False, 'error': 'Need at least 2 hands'}), 400

        # Create job
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

        # Start background thread
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
            max_wait = 300  # 5 minutes timeout
            start_time = time.time()

            while True:
                if time.time() - start_time > max_wait:
                    yield f"data: {json.dumps('__TIMEOUT__')}\n\n"
                    break

                with jobs_lock:
                    job = jobs_store.get(job_id)
                    if not job:
                        yield f"data: {json.dumps('__ERROR__ Job not found')}\n\n"
                        break

                    # Send new output lines
                    output = job['output']
                    if len(output) > last_line:
                        for line in output[last_line:]:
                            yield f"data: {json.dumps(line)}\n\n"
                        last_line = len(output)

                    # Check if job is done
                    if job['status'] in ('completed', 'error'):
                        if job['status'] == 'error':
                            yield f"data: {json.dumps('__ERROR__ ' + job.get('error', 'Unknown error'))}\n\n"
                        exit_code = 1 if job['status'] == 'error' else 0
                        yield f"data: {json.dumps(f'__EXIT__{exit_code}__')}\n\n"
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
