"""In-process equity engine (eval7). Pure functions, no Flask deps, no subprocess.

Algorithm lifted from ENGINEENGINE/source/scripts/plo*-max.py: PLO best-hand =
max over (choose 2 from hole) x (choose 3 from board) of eval7.evaluate().
NLHE best-hand = eval7.evaluate(hand + board) directly (best-5 built in).

eval7 is imported LAZILY inside functions so the app boots even if it's missing
(/api/engine/status then reports offline, /api/equity returns 503).
"""

from __future__ import annotations

from itertools import combinations
from random import sample
from time import perf_counter
from typing import Optional

RANKS = "23456789TJQKA"
SUITS = "hdcs"

RUNOUT_CAP = 200_000

try:
    import eval7  # guarded — app boots without it (status reports offline)
except ImportError:  # pragma: no cover
    eval7 = None


class EquityError(ValueError):
    pass


def _parse_card(token: str):
    """'Ah' -> eval7.Card; tolerates '10s' -> 'Ts'. Raises EquityError on junk."""
    if eval7 is None:
        raise EquityError("eval7 not installed")
    t = token.strip()
    if t[:2] == "10":
        t = "T" + t[2:]
    if len(t) != 2 or t[0] not in RANKS or t[1] not in SUITS:
        raise EquityError(f"bad card: {token!r}")
    try:
        return eval7.Card(t)
    except Exception:
        raise EquityError(f"bad card: {token!r}")


def _hole_n(variant: str) -> int:
    v = (variant or "").lower()
    if v == "nlhe" or v.startswith("nl"):
        return 2
    if v.startswith("plo"):
        digits = [c for c in v.split("-")[0] if c.isdigit()]
        n = int("".join(digits)) if digits else 4
        if n in (4, 5, 6):
            return n
    raise EquityError(f"unknown variant: {variant!r} (use nlhe, plo4, plo5, plo6)")


def _best(hand, board, hole_n: int) -> int:
    if eval7 is None:
        raise EquityError("eval7 not installed")
    if hole_n == 2:
        return eval7.evaluate(list(hand) + list(board))
    best = -1
    for h2 in combinations(hand, 2):
        for b3 in combinations(board, 3):
            best = max(best, eval7.evaluate(list(h2) + list(b3)))
    return best


def equity(hands, board, variant: str, samples: Optional[int] = None) -> dict:
    """Exact (or sampled) equity for N hands on a board.

    hands: list of card-token lists, e.g. [["Ah","Kh"],["Ad","Kd"]]
    board: list of card tokens (0-5), e.g. ["Qs","Js","Ts"]
    Returns {equity:[...], wins:[...], ties:[...], samples, exact, runtime_ms, variant}
    """
    t0 = perf_counter()
    import eval7  # lazy — app boots without it
    assert eval7 is not None  # pragma: no cover — import above guarantees it

    hole_n = _hole_n(variant)
    if len(hands) < 2:
        raise EquityError("need at least 2 hands")
    if len(hands) > 9:
        raise EquityError("max 9 hands")

    seen = set()
    parsed_hands, parsed_board = [], []
    for h in hands:
        if len(h) != hole_n:
            raise EquityError(f"hand {h} has {len(h)} cards, expected {hole_n} for {variant}")
        ph = []
        for tok in h:
            c = _parse_card(tok)
            if c in seen:
                raise EquityError(f"duplicate card: {tok}")
            seen.add(c)
            ph.append(c)
        parsed_hands.append(ph)
    for tok in board:
        c = _parse_card(tok)
        if c in seen:
            raise EquityError(f"duplicate card: {tok}")
        seen.add(c)
        parsed_board.append(c)
    if len(parsed_board) > 5:
        raise EquityError("board max 5 cards")

    deck = [eval7.Card(r + s) for r in RANKS for s in SUITS if eval7.Card(r + s) not in seen]
    board_needed = 5 - len(parsed_board)

    if samples and samples > 0 and board_needed > 0:
        iterable = (sample(deck, board_needed) for _ in range(samples))
        exact = False
    else:
        iterable = combinations(deck, board_needed)
        exact = True

    nhands = len(hands)
    contrib = [0.0] * nhands
    wins = [0] * nhands
    ties = [0] * nhands
    n = 0
    for fill in iterable:
        full = parsed_board + list(fill)
        scores = [_best(h, full, hole_n) for h in parsed_hands]
        top = max(scores)
        top_idx = [i for i, s in enumerate(scores) if s == top]
        share = 1.0 / len(top_idx)
        for i in top_idx:
            contrib[i] += share
            if len(top_idx) == 1:
                wins[i] += 1
            else:
                ties[i] += 1
        n += 1
        if n >= RUNOUT_CAP:
            exact = False
            break

    if n == 0:
        raise EquityError("no runouts (deck exhausted)")

    return {
        "variant": variant,
        "equity": [round(c / n * 100, 2) for c in contrib],
        "wins": wins,
        "ties": ties,
        "samples": n,
        "exact": exact,
        "runtime_ms": round((perf_counter() - t0) * 1000, 1),
    }
