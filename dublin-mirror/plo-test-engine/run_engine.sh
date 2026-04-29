#!/usr/bin/env bash
cd "$(dirname "$0")"

# Load environment configuration
source "/opt/deploy/config/test.env"

# Override with deployment-specific settings
export PLO_SCRIPTS_DIR="/opt/plo-test/engine/scripts"

# Start application - bind to 0.0.0.0 so Docker can access it
exec "/opt/plo-equity/venv/bin/python3" -m gunicorn \
    --workers 8 \
    --worker-class eventlet \
    --bind 0.0.0.0:$APP_PORT \
    --timeout 3600 \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    app:app
