#!/bin/bash
# healthcheck.sh - Check plo-w4p health, restart if down
# Location: /opt/plo-w4p/healthcheck.sh
# Cron: */5 * * * * /opt/plo-w4p/healthcheck.sh >> /var/log/plo-w4p-health.log 2>&1

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

# Check if the health endpoint responds with HTTP 200
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:5003/api/health 2>/dev/null)

if [ "$HTTP_CODE" = "200" ]; then
    # Healthy - no action needed (only log failures to avoid log spam)
    exit 0
fi

echo "$LOG_PREFIX ALERT: plo-w4p health check failed (HTTP $HTTP_CODE). Restarting..."

# Restart via systemd
sudo systemctl restart plo-w4p

# Wait for startup
sleep 3

# Verify restart worked
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:5003/api/health 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    echo "$LOG_PREFIX RECOVERY: plo-w4p restarted successfully (HTTP $HTTP_CODE)"
else
    echo "$LOG_PREFIX CRITICAL: plo-w4p restart FAILED (HTTP $HTTP_CODE). Manual intervention needed."
fi
