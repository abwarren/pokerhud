"""Selector registry tests — slice 4c (hermetic: no DB, pure functions)."""

import json

import pytest

from webapp.selector_registry import (
    SelectorRegistryError,
    load_profiles,
    registry_status,
)


def test_profiles_load_and_validate(tmp_path):
    (tmp_path / "evenbet.json").write_text(json.dumps({
        "site": "sunbet",
        "domains": ["sb-play.pkrsrv.com"],
        "seatSel": ".r-seat",
        "nameSel": ".player-name",
        "stackSel": ".player-cash",
        "boardSel": ".r-table-cards .r-card .face",
        "potSel": ".bank-container-content",
        "canvasTable": False,
    }))
    (tmp_path / "betconstruct.json").write_text(json.dumps({
        "site": "pokerbet",
        "domains": ["poker-web.pokerbet.co.za"],
        "seatSel": "[class*=seat]",
        "nameSel": "[class*=name]",
        "stackSel": "[class*=stack]",
        "boardSel": "[class*=board] [class*=card]",
        "potSel": "[class*=pot]",
        "canvasTable": True,
    }))
    profiles = load_profiles(tmp_path)
    assert set(profiles) == {"evenbet.json", "betconstruct.json"}
    assert profiles["evenbet.json"]["site"] == "sunbet"
    assert profiles["betconstruct.json"]["site"] == "pokerbet"


def test_missing_file_raises(tmp_path):
    with pytest.raises(SelectorRegistryError):
        load_profiles(tmp_path)  # neither profile present


def test_invalid_site_rejected(tmp_path):
    (tmp_path / "evenbet.json").write_text(json.dumps({
        "site": "badbet", "domains": ["x.com"], "seatSel": "a", "nameSel": "b",
        "stackSel": "c", "boardSel": "d", "potSel": "e", "canvasTable": False,
    }))
    (tmp_path / "betconstruct.json").write_text(json.dumps({
        "site": "pokerbet", "domains": ["x.com"], "seatSel": "a", "nameSel": "b",
        "stackSel": "c", "boardSel": "d", "potSel": "e", "canvasTable": True,
    }))
    with pytest.raises(SelectorRegistryError):
        load_profiles(tmp_path)


def test_malformed_json_raises(tmp_path):
    (tmp_path / "evenbet.json").write_text("{not json")
    (tmp_path / "betconstruct.json").write_text("{}")
    with pytest.raises(SelectorRegistryError):
        load_profiles(tmp_path)


def test_registry_status_non_raising(tmp_path):
    status = registry_status(tmp_path)  # empty dir -> not ok, no raise
    assert status["ok"] is False
    assert "error" in status
