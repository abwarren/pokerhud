#!/usr/bin/env bash
# ============================================================
# PokerHUD 10K+ Tournament Scraper — Cron Runner
# Discovers the daily schedule & scrapes 10K+ tables
# ============================================================
set -euo pipefail

cd /home/wa/projects/poker/pokerhud
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG="scraped_data/cron_10k.log"

echo "[$TIMESTAMP] === 10K+ scrap cycle ===" >> "$LOG"

# Run the table scraper (filters to 10K+ via classify_tournament)
python3 table_scraper.py >> "$LOG" 2>&1

echo "[$TIMESTAMP] Done" >> "$LOG"
cat "$LOG" | tail -5
