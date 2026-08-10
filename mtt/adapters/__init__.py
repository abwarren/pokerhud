"""Site adapter protocol. Each site implements the same canonical interface;
internal implementation may differ completely.

Methods return dicts in adapter conventions; the pipeline normalizes them.

    discover() -> list[dict]
        Tournament schedule: each dict has at least name/start_time/buyin/status.
    snapshot(ref) -> dict | None
        Lifecycle snapshot of one tournament (entries, blinds, prize pool, ...).
    results(ref) -> dict | None
        Final results: winners, payouts, finishing positions (if exposed).
    hand_data(ref) -> list[dict]
        Hand history where the source exposes it (later phase; default []).
"""

from __future__ import annotations

from typing import Optional


class SiteAdapter:
    site: str = "base"

    def discover(self) -> list:
        raise NotImplementedError

    def snapshot(self, ref: str) -> Optional[dict]:
        return None

    def results(self, ref: str) -> Optional[dict]:
        return None

    def hand_data(self, ref: str) -> list:
        return []


def get_adapter(site: str, **kwargs) -> SiteAdapter:
    site = site.lower()
    if site == "pokerbet":
        from .pokerbet import PokerBetAdapter
        return PokerBetAdapter(**kwargs)
    if site == "sunbet":
        from .sunbet import SunBetAdapter
        return SunBetAdapter(**kwargs)
    raise ValueError(f"unknown site adapter: {site}")


class FixtureAdapter(SiteAdapter):
    """Replays recorded payloads — deterministic E2E without network."""

    site = "fixture"

    def __init__(self, site: str, fixtures: list, snapshots: Optional[dict] = None,
                 results_map: Optional[dict] = None):
        self.site = site
        self.fixtures = fixtures          # list of raw tournament payloads
        self.snapshots = snapshots or {}  # ref -> list of snapshot payloads
        self.results_map = results_map or {}  # ref -> results payload

    def discover(self) -> list:
        return list(self.fixtures)

    def snapshot(self, ref: str) -> Optional[dict]:
        snaps = self.snapshots.get(ref)
        if not snaps:
            return None
        return snaps.pop(0) if snaps else None

    def results(self, ref: str) -> Optional[dict]:
        return self.results_map.get(ref)
