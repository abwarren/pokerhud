"""Test helpers: fixture loading + schema reset (mtt_test)."""

import json
import os
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    with open(FIXTURES / name) as f:
        return json.load(f)


def reset_schema(conn):
    s = os.environ["MTT_SCHEMA"]
    # children first (FK order)
    tables = [
        "hand_actions", "hand_players", "hands", "table_snapshots", "tables",
        "tournament_cohorts", "tournament_snapshots", "player_tournaments",
        "player_aliases", "players", "tournaments", "raw_events",
        "parser_errors", "ingestion_runs", "daily_statistics",
    ]
    with conn.cursor() as cur:
        for t in tables:
            cur.execute(f"DELETE FROM {s}.{t}")
    conn.commit()
