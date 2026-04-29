#!/bin/bash
# EIP SNAT + Policy Routing for Multi-ENI Setup
# Updated: 2026-04-15 — kele1 only (1 EIP available)
#
# ens5 (primary): 172.31.17.239 → 52.16.14.220 (Remote Control + nginx)
# ens6: kele1 (172.18.0.2) → 52.30.108.218 via 172.31.22.196

set -e

# Flush existing SNAT rules for containers (keep MASQUERADE)
iptables -t nat -S POSTROUTING | grep "172.18.0" | grep SNAT | while read rule; do
  iptables -t nat $(echo "$rule" | sed s/^-A/-D/) 2>/dev/null || true
done

# Flush existing mangle marks for containers
iptables -t mangle -S PREROUTING | grep "172.18.0" | while read rule; do
  iptables -t mangle $(echo "$rule" | sed s/^-A/-D/) 2>/dev/null || true
done

# Remove old ip rules
ip rule del fwmark 101 2>/dev/null || true

# === kele1: 172.18.0.2 → ens6 → 52.30.108.218 ===
iptables -t mangle -A PREROUTING -s 172.18.0.2 -j MARK --set-mark 101
ip rule add fwmark 101 lookup 101 prio 100
ip route replace default via 172.31.16.1 dev ens6 table 101
ip route replace 172.31.16.0/20 dev ens6 scope link table 101
iptables -t nat -I POSTROUTING -s 172.18.0.2 -o ens6 -j SNAT --to-source 172.31.22.196

echo "EIP SNAT applied at $(date) — kele1 → 52.30.108.218"
