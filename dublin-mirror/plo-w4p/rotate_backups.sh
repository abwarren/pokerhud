#!/bin/bash
# Rotate app.py backups — keep only last 3
cd /opt/plo-w4p
BAK_COUNT=$(ls -1 app.py.bak.* 2>/dev/null | wc -l)
if [ "$BAK_COUNT" -gt 3 ]; then
    ls -1 app.py.bak.* | sort -n | head -n -3 | xargs rm -f
fi
# Also rotate health log (keep last 1000 lines)
if [ -f /var/log/plo-w4p-health.log ]; then
    tail -1000 /var/log/plo-w4p-health.log > /var/log/plo-w4p-health.log.tmp
    mv /var/log/plo-w4p-health.log.tmp /var/log/plo-w4p-health.log
fi
