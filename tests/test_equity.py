"""Regression tests for the in-process equity engine (webapp.equity).

Hermetic: pure functions only — no DB, no Flask. Guards the fix for the
"bad card: 'Ah'" bug (eval7 lazy-import scope: NameError was swallowed into
EquityError by the bare except in _parse_card).
"""

import pytest

from webapp.equity import EquityError, equity


def test_parse_valid_cards_nlhe():
    """The exact regression: 'Ah' must parse (eval7 import scope bug)."""
    r = equity([["Ah", "As"], ["Kh", "Ks"]], [], "nlhe", samples=2000)
    assert r["equity"][0] > r["equity"][1]  # AA > KK
    assert r["variant"] == "nlhe"
    assert len(r["equity"]) == 2


def test_ten_cards_tolerated():
    """'10h' style tokens are normalised to 'Th'."""
    r = equity([["10h", "10d"], ["As", "Ks"]], [], "nlhe", samples=2000)
    assert len(r["equity"]) == 2


def test_plo5_exact():
    r = equity(
        [["Ah", "Kh", "Qh", "Jh", "Th"], ["Ad", "Kd", "Qd", "Jd", "Td"]],
        ["2c", "7s", "9d"],
        "plo5",
    )
    assert r["exact"] is True
    assert sum(r["equity"]) == pytest.approx(100.0, abs=0.1)


def test_sampled_runout():
    r = equity([["Ah", "Kh"], ["Ad", "Kd"]], ["Qs", "Js", "Ts"], "nlhe", samples=1000)
    assert r["exact"] is False
    assert r["samples"] == 1000
    assert r["equity"] == [50.0, 50.0]  # identical hands -> dead even


def test_error_paths():
    with pytest.raises(EquityError):
        equity([["Ah"]], [], "nlhe")  # 1 card hand
    with pytest.raises(EquityError):
        equity([["Ah", "Kh", "Qh", "Jh"]], [], "plo4")  # 4-card variant needs 4
    with pytest.raises(EquityError):
        equity([["Ah", "Kh"], ["Ad", "Kd"]], ["Zs"], "nlhe")  # junk board card
    with pytest.raises(EquityError):
        equity([["Ah", "Ah"], ["Ad", "Kd"]], [], "nlhe")  # duplicate
    with pytest.raises(EquityError):
        equity([["Ah", "Kh"]], [], "badvariant")  # unknown variant


def test_board_cap():
    with pytest.raises(EquityError):
        equity([["Ah", "Kh"], ["Ad", "Kd"]], ["2c", "3c", "4c", "5c", "6c", "7c"], "nlhe")
