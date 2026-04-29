"""
Windows Instance Manager - API routes for stop/start/status of Windows EC2 instances.
Registered in app.py via register_windows_routes(app).
Uses session-based auth via the engine login (port 5055/5050).
"""
import boto3
import logging
from functools import wraps
from flask import jsonify, request, session

logger = logging.getLogger(__name__)

REGION = 'eu-west-1'

INSTANCES = {
    '1': {'id': 'i-0efb226913ca37522', 'name': 'Windows-1'},
    '2': {'id': 'i-04b9d9bc12f1379e2', 'name': 'Windows-2'},
    '3': {'id': 'i-00704611d616fcef5', 'name': 'Windows-3'},
    '4': {'id': 'i-0e60aacd2cd3ca4f3', 'name': 'Windows-4'},
    '5': {'id': 'i-0727e4a797884e86b', 'name': 'Windows-5'},
    '6': {'id': 'i-05311e954c033a6a1', 'name': 'Windows-6'},
    '7': {'id': 'i-0d2c9831434c6bca7', 'name': 'Windows-7'},
    '8': {'id': 'i-086590d67f1adc04a', 'name': 'Windows-8'},
}

ALL_IDS = [v['id'] for v in INSTANCES.values()]

# Simple API key for windows management (checked in request header)
API_KEY = 'n4p-windows-mgmt-2026'

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key', '')
        if key != API_KEY:
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

def _ec2():
    return boto3.client('ec2', region_name=REGION)

def _get_status():
    ec2 = _ec2()
    resp = ec2.describe_instances(InstanceIds=ALL_IDS)
    results = {}
    for res in resp['Reservations']:
        for inst in res['Instances']:
            iid = inst['InstanceId']
            name = next((t['Value'] for t in inst.get('Tags', []) if t['Key'] == 'Name'), iid)
            num = next((k for k, v in INSTANCES.items() if v['id'] == iid), '?')
            results[num] = {
                'num': num,
                'id': iid,
                'name': name,
                'state': inst['State']['Name'],
                'ip': inst.get('PublicIpAddress', None),
                'type': inst['InstanceType'],
                'launch_time': inst.get('LaunchTime', '').isoformat() if inst.get('LaunchTime') else None,
            }
    return dict(sorted(results.items()))


def register_windows_routes(app):

    @app.route('/api/windows/status', methods=['GET'])
    @require_api_key
    def windows_status():
        try:
            status = _get_status()
            return jsonify({'ok': True, 'instances': status})
        except Exception as e:
            logger.error(f'[Windows] Status error: {e}')
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app.route('/api/windows/stop', methods=['POST'])
    @require_api_key
    def windows_stop():
        try:
            data = request.get_json() or {}
            targets = data.get('targets', [])
            if not targets:
                return jsonify({'ok': False, 'error': 'No targets specified'}), 400
            ids = []
            for t in targets:
                t = str(t)
                if t in INSTANCES:
                    ids.append(INSTANCES[t]['id'])
                else:
                    return jsonify({'ok': False, 'error': f'Unknown instance: {t}'}), 400
            ec2 = _ec2()
            resp = ec2.stop_instances(InstanceIds=ids)
            changes = []
            for ch in resp.get('StoppingInstances', []):
                changes.append({
                    'id': ch['InstanceId'],
                    'prev': ch['PreviousState']['Name'],
                    'current': ch['CurrentState']['Name'],
                })
            logger.info(f'[Windows] Stopped: {targets}')
            return jsonify({'ok': True, 'changes': changes})
        except Exception as e:
            logger.error(f'[Windows] Stop error: {e}')
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app.route('/api/windows/start', methods=['POST'])
    @require_api_key
    def windows_start():
        try:
            data = request.get_json() or {}
            targets = data.get('targets', [])
            if not targets:
                return jsonify({'ok': False, 'error': 'No targets specified'}), 400
            ids = []
            for t in targets:
                t = str(t)
                if t in INSTANCES:
                    ids.append(INSTANCES[t]['id'])
                else:
                    return jsonify({'ok': False, 'error': f'Unknown instance: {t}'}), 400
            ec2 = _ec2()
            resp = ec2.start_instances(InstanceIds=ids)
            changes = []
            for ch in resp.get('StartingInstances', []):
                changes.append({
                    'id': ch['InstanceId'],
                    'prev': ch['PreviousState']['Name'],
                    'current': ch['CurrentState']['Name'],
                })
            logger.info(f'[Windows] Started: {targets}')
            return jsonify({'ok': True, 'changes': changes})
        except Exception as e:
            logger.error(f'[Windows] Start error: {e}')
            return jsonify({'ok': False, 'error': str(e)}), 500
