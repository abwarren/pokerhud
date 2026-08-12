"""Auto-actions decision engine (slice 7 / PLAN TB-004).

Pure functions — no Flask, no state. Decides the next action for a hero
given a per-table rule and the actions the DOM currently exposes.

Rules (per PLAN.md slice 4):
  off  — disabled
  cf   — check/fold: check when free, fold when facing a bet
  cc   — check/call: check when free, call when facing a bet
  kh   — Knallhard: always bet/raise (min size), call/check only as fallback
"""

from __future__ import annotations

from typing import List, Optional

RULES = ("off", "cf", "cc", "kh")
VALID_ACTIONS = ("fold", "check", "call", "bet", "raise")

# Canonical command types accepted by the command queue (remote_bp).
CMD_TYPES = ("fold", "check", "call", "bet", "raise")


class AutoActionError(ValueError):
    pass


def normalize_actions(actions) -> List[str]:
    """Lowercase + dedupe + keep known actions. Tolerates junk input."""
    if not actions:
        return []
    out = []
    for a in actions:
        s = str(a).strip().lower()
        if s in VALID_ACTIONS and s not in out:
            out.append(s)
    return out


def validate_rule(rule) -> str:
    r = (rule or "off").strip().lower()
    if r not in RULES:
        raise AutoActionError(f"unknown auto rule {rule!r} (use {', '.join(RULES)})")
    return r


def decide(rule: str, actions) -> Optional[dict]:
    """Return a command dict ({type, amount}) to queue, or None.

    Returns None when: rule off, no usable action, or the hero cannot act
    (no available actions reported).
    """
    r = validate_rule(rule)
    a = normalize_actions(actions)
    if r == "off" or not a:
        return None

    if r == "cf":
        if "check" in a:
            return {"type": "check", "amount": None}
        if "fold" in a:
            return {"type": "fold", "amount": None}
        return None  # facing bet with only call/raise → hands off

    if r == "cc":
        if "check" in a:
            return {"type": "check", "amount": None}
        if "call" in a:
            return {"type": "call", "amount": None}
        return None  # cannot check or call → hands off

    # kh — Knallhard
    if "raise" in a:
        return {"type": "raise", "amount": None}  # None = minimum raise
    if "bet" in a:
        return {"type": "bet", "amount": None}
    if "call" in a:
        return {"type": "call", "amount": None}
    if "check" in a:
        return {"type": "check", "amount": None}
    return None
