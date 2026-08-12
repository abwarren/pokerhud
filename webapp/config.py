"""Merged app configuration — all env-driven, repo-local defaults.

Replaces the legacy /opt/plo-equity hardcodes. Credentials follow the canonical
mtt pattern (env MTT_* + ~/.pokerhud_pgpass) — never secrets in source.
"""

from pathlib import Path
import os

BASE = Path(__file__).parent

# Runtime state (gitignored)
STATE_FILE      = Path(os.getenv("N4P_STATE_FILE", BASE / "var" / "state_snapshot.json"))
COLLECTOR_DIR   = Path(os.getenv("COLLECTOR_DIR", BASE / "var" / "hand-collector"))
SAVE_DIR        = COLLECTOR_DIR / "saved_hands"

STATIC_DIR      = Path(os.getenv("STATIC_DIR", str(BASE / "static")))

# API key — required for snapshot/commands (w4p.js sends it; empty default means
# "must be set in env" — the key is never shipped in source).
TRACKER_API_KEY = os.getenv("TRACKER_API_KEY", "")
N4P_SEAT_SECRET = os.getenv("N4P_SEAT_SECRET", "")

SEAT_TTL  = 30
CMD_TTL   = 30
PERSIST_INT = 10

PORT = int(os.getenv("PORT", "8899"))
