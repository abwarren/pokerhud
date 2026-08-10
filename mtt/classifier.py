"""Tournament classification: buy-in bands, field bands, R1000 cohort.

Rules (plan docs/mtt-pipeline-plan.md):
- buyin_band by buy-in ZAR (entry cost, excluding fee):
    < 100            MICRO
    100 – 499        SMALL
    500 – 999        MID
    1000             R1000   <- dedicated cohort, NEVER mixed in analytics
    > 1000           HIGH
- field_band by entries/field size:
    1–50     TINY_FIELD
    51–150   SMALL_FIELD
    151–500  MEDIUM_FIELD
    501–999  LARGE_FIELD
    >=1000   1000_PLUS_FIELD
- cohort = 'R1000' when buyin_band == 'R1000', else buyin_band value.

Fallback: if buyin is missing, classify from total_entry_cost; if neither,
band is UNKNOWN (flagged by the quality engine, never guessed).
"""

from __future__ import annotations

from typing import Optional

# Ordered band boundaries (lower bound inclusive). R1000 is its own exact band.
BUYIN_BANDS = [
    (None, 100, "MICRO"),
    (100, 500, "SMALL"),
    (500, 1000, "MID"),
    (1000, 1000, "R1000"),      # exact: buyin == 1000
    (1000, None, "HIGH"),       # > 1000
]

FIELD_BANDS = [
    (1, 51, "TINY_FIELD"),
    (51, 151, "SMALL_FIELD"),
    (151, 501, "MEDIUM_FIELD"),
    (501, 1000, "LARGE_FIELD"),
    (1000, None, "1000_PLUS_FIELD"),
]

R1000_BUYIN = 1000


def classify_buyin(buyin: Optional[float]) -> Optional[str]:
    """Return buyin_band for a numeric buy-in (ZAR). None -> UNKNOWN."""
    if buyin is None:
        return None
    if buyin == R1000_BUYIN:
        return "R1000"
    if buyin < 100:
        return "MICRO"
    if buyin < 500:
        return "SMALL"
    if buyin < 1000:
        return "MID"
    return "HIGH"


def classify_field(entries: Optional[int]) -> Optional[str]:
    """Return field_band for an entries/field count. None -> UNKNOWN."""
    if entries is None or entries <= 0:
        return None
    if entries < 51:
        return "TINY_FIELD"
    if entries < 151:
        return "SMALL_FIELD"
    if entries < 501:
        return "MEDIUM_FIELD"
    if entries < 1000:
        return "LARGE_FIELD"
    return "1000_PLUS_FIELD"


def cohort_for(buyin_band: Optional[str]) -> Optional[str]:
    """Analytics cohort. R1000 stays isolated; others carry their band."""
    if buyin_band is None:
        return None
    if buyin_band == "R1000":
        return "R1000"
    return buyin_band


def classify_tournament(t: dict) -> dict:
    """Add buyin_band/field_band/cohort to a canonical tournament dict.

    Mutates and returns the dict. Uses buyin first, total_entry_cost as
    fallback (flagged as inferred by the caller via 'buyin_inferred').
    """
    buyin = t.get("buyin")
    if buyin is None and t.get("total_entry_cost") is not None:
        buyin = t["total_entry_cost"]
        t["buyin_inferred"] = True
    band = classify_buyin(buyin)
    t["buyin_band"] = band
    t["buyin_inferred"] = t.get("buyin_inferred", False)

    entries = t.get("entries")
    if entries is None:
        entries = t.get("field_size")
    t["field_band"] = classify_field(entries)
    t["cohort"] = cohort_for(band)
    return t
