"""Data quality engine: flags + 0-100 score per tournament.

Flags are explicit; gaps are never silently filled. Score starts at 100
and deducts for missing/contradictory data:

    -25  missing identity (site_tournament_id or name)
    -25  missing buy-in (or buyin_band UNKNOWN)
    -15  missing start_time
    -10  missing field_size AND entries
    -10  missing prize_pool
    -10  missing status
    -10  status completed but no finish data / contradictory counts
     -5  inferred value used
"""

from __future__ import annotations

CRITICAL_ID = "MISSING_IDENTITY"
CRITICAL_BUYIN = "MISSING_BUYIN"
CRITICAL_TIME = "MISSING_START_TIME"
MISSING_FIELD_SIZE = "MISSING_FIELD_SIZE"
MISSING_PRIZE_POOL = "MISSING_PRIZE_POOL"
MISSING_STATUS = "MISSING_STATUS"
PARTIAL_CAPTURE = "PARTIAL_CAPTURE"
INFERRED_VALUE = "INFERRED_VALUE"
DUPLICATE_EVENT = "DUPLICATE_EVENT"
PARSER_ERROR = "PARSER_ERROR"
CONTRADICTION = "DATA_MISMATCH"
NO_RESULTS = "NO_RESULTS"

WEIGHTS = {
    CRITICAL_ID: 25,
    CRITICAL_BUYIN: 25,
    CRITICAL_TIME: 15,
    MISSING_FIELD_SIZE: 10,
    MISSING_PRIZE_POOL: 10,
    MISSING_STATUS: 10,
    PARTIAL_CAPTURE: 5,
    INFERRED_VALUE: 5,
    DUPLICATE_EVENT: 10,
    PARSER_ERROR: 25,
    CONTRADICTION: 10,
    NO_RESULTS: 15,
}


def score_tournament(t: dict, extra: dict | None = None) -> tuple[int, list[str]]:
    """Return (score 0-100, flags list) for a canonical tournament dict.

    extra: optional context dict, e.g. {"no_results": True} when a completed
    tournament's results capture produced no finishing data.
    """
    extra = extra or {}
    flags = []
    if not t.get("site_tournament_id") or not t.get("name"):
        flags.append(CRITICAL_ID)
    if t.get("buyin") is None and not t.get("buyin_inferred"):
        flags.append(CRITICAL_BUYIN)
    if t.get("start_time") is None:
        flags.append(CRITICAL_TIME)
    if t.get("field_size") is None and t.get("entries") is None:
        flags.append(MISSING_FIELD_SIZE)
    if t.get("prize_pool") is None:
        flags.append(MISSING_PRIZE_POOL)
    if t.get("status") is None:
        flags.append(MISSING_STATUS)
    if t.get("buyin_inferred"):
        flags.append(INFERRED_VALUE)
    # Contradictions: completed tournaments should have final numbers.
    if t.get("status") == "completed":
        if t.get("entries") and t.get("field_size") and t["entries"] < t["field_size"]:
            flags.append(CONTRADICTION)
        if t.get("prize_pool") is None:
            flags.append(CONTRADICTION)
        # prize pool below the guaranteed floor for a finished event is a red flag
        if (t.get("prize_pool") is not None and t.get("guarantee") is not None
                and t["prize_pool"] < t["guarantee"] * 0.9):
            flags.append(CONTRADICTION)
    if isinstance(t.get("field_size"), int) and t["field_size"] > 0 and t.get("entries") is None:
        flags.append(PARTIAL_CAPTURE)
    if extra.get("no_results"):
        flags.append(NO_RESULTS)

    score = 100
    for f in flags:
        score -= WEIGHTS.get(f, 0)
    return max(score, 0), flags


def completeness_level(score: int) -> str:
    if score >= 90:
        return "complete"
    if score >= 60:
        return "partial"
    return "incomplete"
