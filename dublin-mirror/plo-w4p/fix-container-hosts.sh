#!/bin/bash
# Ensure bot containers can reach potlimitomaha.xyz via Docker gateway
# (Avoids hairpin NAT issue where containers cant reach hosts public EIP)
for c in $(docker ps --filter "name=bot-" --format "{{.Names}}" 2>/dev/null); do
    docker exec -u root "$c" sh -c "grep -q potlimitomaha /etc/hosts 2>/dev/null || echo 172.18.0.1 potlimitomaha.xyz >> /etc/hosts" 2>/dev/null
done
