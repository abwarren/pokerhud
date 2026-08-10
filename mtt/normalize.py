"""Normalization: adapter output -> canonical tournament records.

Adapters return dicts with their own key conventions. normalize() maps to
the canonical field set, cleans values (currency symbols, thousands
separators, casing), and never fabricates missing data.

Canonical tournament fields:
    site, site_tournament_id, name, game_type, format, currency,
    buyin, fee, total_entry_cost, guarantee, start_time, status,
    field_size, unique_players, entries, reentries, prize_pool,
    max_players, structure_hash, detected_players

Canonical snapshot fields:
    captured_at, status, entries, players_remaining, tables_active,
    prize_pool, current_level, small_blind, big_blind, ante,
    average_stack, late_registration
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

# Statuses are free-form at the source; map to canonical set.
STATUS_MAP = {
    "scheduled": "scheduled",
    "registration": "registration",
    "open": "registration",
    "late registration": "late_reg",
    "late registration open": "late_reg",
    "late reg": "late_reg",
    "running": "running",
    "in progress": "running",
    "started": "running",
    "completed": "completed",
    "finished": "completed",
    "ended": "completed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}

GAME_TYPES = {"NLHE", "PLO", "PLO5", "FLHE", "HORSE", "8GAME", "MIXED", "NLH"}


def clean_money(v) -> Optional[int]:
    """'R1,250' / 'R 1 250' / '1250.00' / 'R1M' / '10k' / 1250 -> ZAR int."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(round(v))
    s = str(v).strip()
    if not s:
        return None
    s = re.sub(r"[Rr\s,]", "", s).strip()  # currency symbol, spaces, commas
    if not s:
        return None
    if re.search(r"\.\d{1,2}$", s):       # trailing decimal (1250.00, 1250.5)
        s = s.rsplit(".", 1)[0]
    else:
        s = s.replace(".", "")            # dots as thousands separators
    if not s:
        return None
    mult = 1
    low = s.lower()
    if low.endswith("m"):
        mult, s = 1_000_000, s[:-1]
    elif low.endswith("k"):
        mult, s = 1_000, s[:-1]
    try:
        return int(round(float(s) * mult))
    except ValueError:
        return None


def clean_int(v) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return int(re.sub(r"[^\d]", "", s)) if re.search(r"\d", s) else None
    except ValueError:
        return None


def clean_name(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def normalize_status(v) -> Optional[str]:
    if v is None:
        return None
    return STATUS_MAP.get(str(v).strip().lower(), str(v).strip().lower())


GAME_TYPES = {"NLHE", "PLO", "PLO5", "FLHE", "HORSE", "8GAME", "MIXED", "NLH"}

# Explicit aliases -> canonical type (checked before substring matching).
GAME_ALIASES = {
    "NL HOLD'EM": "NLHE", "NL HOLDEM": "NLHE", "NLH": "NLHE",
    "TEXAS HOLD'EM": "NLHE", "TEXAS HOLDEM": "NLHE", "HOLDEM": "NLHE",
    "NO LIMIT HOLD'EM": "NLHE", "NO LIMIT HOLDEM": "NLHE",
    "POT LIMIT OMAHA": "PLO", "OMAHA HI": "PLO", "OMAHA": "PLO",
    "OMAHA 5": "PLO5", "OMAHA HI-LO": "PLO8", "OMAHA 8": "PLO8",
}


def normalize_game_type(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().upper()
    if s in GAME_ALIASES:
        return GAME_ALIASES[s]
    for g in sorted(GAME_TYPES, key=len, reverse=True):  # PLO5 before PLO
        if g in s:
            return g
    return s or None


def parse_datetime(v) -> Optional[str]:
    """Accept ISO strings or epoch millis; return UTC ISO string or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            if v > 1e12:  # millis
                v = v / 1000.0
            return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            return None
    s = str(v).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def normalize_tournament(raw: dict) -> dict:
    """Map an adapter dict to the canonical tournament record.

    Unknown keys are ignored; missing values stay None (quality engine
    flags them). site_tournament_id defaults to a hash of name when the
    source has no id, preserving idempotency for name-only sources.
    """
    site = clean_name(raw.get("site"))
    stid = clean_name(raw.get("site_tournament_id"))
    name = clean_name(raw.get("name"))
    if stid is None and name is not None:
        import hashlib
        stid = "nid-" + hashlib.sha1(f"{site}|{name}".encode()).hexdigest()[:16]

    return {
        "site": site,
        "site_tournament_id": stid,
        "name": name,
        "game_type": normalize_game_type(raw.get("game_type")),
        "format": clean_name(raw.get("format")),
        "currency": clean_name(raw.get("currency")) or "ZAR",
        "buyin": clean_money(raw.get("buyin")),
        "fee": clean_money(raw.get("fee")),
        "total_entry_cost": clean_money(raw.get("total_entry_cost")),
        "guarantee": clean_money(raw.get("guarantee")),
        "start_time": parse_datetime(raw.get("start_time")),
        "status": normalize_status(raw.get("status")),
        "field_size": clean_int(raw.get("field_size")),
        "unique_players": clean_int(raw.get("unique_players")),
        "entries": clean_int(raw.get("entries")),
        "reentries": clean_int(raw.get("reentries")),
        "prize_pool": clean_money(raw.get("prize_pool")),
        "max_players": clean_int(raw.get("max_players")),
        "structure_hash": clean_name(raw.get("structure_hash")),
        "detected_players": raw.get("detected_players") or [],
    }


def normalize_snapshot(raw: dict) -> dict:
    return {
        "captured_at": parse_datetime(raw.get("captured_at")),
        "status": normalize_status(raw.get("status")),
        "entries": clean_int(raw.get("entries")),
        "players_remaining": clean_int(raw.get("players_remaining")),
        "tables_active": clean_int(raw.get("tables_active")),
        "prize_pool": clean_money(raw.get("prize_pool")),
        "current_level": clean_int(raw.get("current_level")),
        "small_blind": clean_int(raw.get("small_blind")),
        "big_blind": clean_int(raw.get("big_blind")),
        "ante": clean_int(raw.get("ante")),
        "average_stack": clean_int(raw.get("average_stack")),
        "late_registration": raw.get("late_registration"),
    }


def normalize_player(raw: dict) -> dict:
    return {
        "site": clean_name(raw.get("site")),
        "site_player_id": clean_name(raw.get("site_player_id")),
        "display_name": clean_name(raw.get("display_name")),
        "normalized_name": clean_name(raw.get("normalized_name")),
        "finish_position": clean_int(raw.get("finish_position")),
        "prize": clean_money(raw.get("prize")),
        "bounty": clean_money(raw.get("bounty")),
        "entry_number": clean_int(raw.get("entry_number")),
        "starting_stack": clean_int(raw.get("starting_stack")),
        "rebuy_count": clean_int(raw.get("rebuy_count")),
        "addon_count": clean_int(raw.get("addon_count")),
    }
