"""Selector registry — startup validation of extension selector profiles.

Slice 4c of the harmonization: fail fast on a corrupt/mis-schemed selector
profile so a site DOM change or bad edit is caught at boot, not silently
during a live scrape.

Profiles live in extension/src/selectors/*.json (schema frozen in
docs/SLICES.md slice 2B): { site, domains[], seatSel, nameSel, stackSel,
boardSel, potSel, canvasTable }.

Policy: unreadable or schema-invalid JSON is a REGISTRY ERROR (the app logs
CRITICAL and the status endpoint reports it); the app still boots so the
dashboard/equity side is never held hostage by the extension side.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

SELECTORS_DIR = Path(__file__).resolve().parent.parent / "extension" / "src" / "selectors"

REQUIRED_FIELDS = ("site", "domains", "seatSel", "nameSel", "stackSel", "boardSel", "potSel")
VALID_SITES = ("pokerbet", "sunbet")
PROFILE_FILES = ("evenbet.json", "betconstruct.json")


class SelectorRegistryError(ValueError):
    pass


def _validate_profile(name: str, data: Dict[str, Any]) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise SelectorRegistryError(f"{name}: missing fields {missing}")
    if data["site"] not in VALID_SITES:
        raise SelectorRegistryError(
            f"{name}: site {data['site']!r} not in {VALID_SITES}"
        )
    if not isinstance(data["domains"], list) or not data["domains"]:
        raise SelectorRegistryError(f"{name}: domains must be a non-empty list")
    for d in data["domains"]:
        if not isinstance(d, str) or not d.strip():
            raise SelectorRegistryError(f"{name}: empty domain entry")
    if not isinstance(data.get("canvasTable"), bool):
        raise SelectorRegistryError(f"{name}: canvasTable must be bool")
    for sel in ("seatSel", "nameSel", "stackSel", "boardSel", "potSel"):
        if not isinstance(data[sel], str) or not data[sel].strip():
            raise SelectorRegistryError(f"{name}: {sel} must be a non-empty string")


def load_profiles(selectors_dir: Path = SELECTORS_DIR) -> Dict[str, Dict[str, Any]]:
    """Load + validate all selector profiles. Raises SelectorRegistryError on any failure."""
    selectors_dir = Path(selectors_dir)  # tolerate str callers
    profiles: Dict[str, Dict[str, Any]] = {}
    for fname in PROFILE_FILES:
        path = selectors_dir / fname
        if not path.exists():
            raise SelectorRegistryError(f"{fname}: file missing in {selectors_dir}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SelectorRegistryError(f"{fname}: invalid JSON — {e}")
        if not isinstance(data, dict):
            raise SelectorRegistryError(f"{fname}: profile must be a JSON object")
        _validate_profile(fname, data)
        profiles[fname] = data
    return profiles


def registry_status(selectors_dir: Path = SELECTORS_DIR) -> Dict[str, Any]:
    """Non-raising status view for /api/selectors/status."""
    try:
        profiles = load_profiles(selectors_dir)
        return {
            "ok": True,
            "profiles": {
                fname: {"site": p["site"], "domains": p["domains"], "canvasTable": p["canvasTable"]}
                for fname, p in profiles.items()
            },
        }
    except SelectorRegistryError as e:
        return {"ok": False, "error": str(e)}
