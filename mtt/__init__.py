"""mtt — Multi-Tier Tournament pipeline for PokerHUD (SunBet + PokerBet).

Canonical tournament data capture: raw preservation, normalization,
band/cohort classification (R1000 isolated), idempotent Postgres writes,
daily reconciliation.
"""

PARSER_VERSION = "1.0.0"
DEFAULT_RAW_DIR = "raw"
SA_TZ = "Africa/Johannesburg"
