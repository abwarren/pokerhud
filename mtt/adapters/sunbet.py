"""SunBet adapter — EvenBet Gaming PokerAlpha platform (sb-play.pkrsrv.com).

Sources:
1. Lobby tournament rows + per-tournament detail panels. The EvenBet SPA
   renders the schedule in the DOM only (virtual scrolling), so live capture
   needs a browser session with SunBet cookies. Two collection modes:
   - browser: Selenium collector scrapes lobby rows + detail panels and
     produces EvenBet-shaped payloads (see SunBetBrowserCollector).
   - files:   EvenBet-shaped JSON payloads placed in MTT_SB_INPUT are parsed
     and ingested by the same parsers (deterministic, cron-friendly).
2. The pure parsers parse_lobby_rows()/parse_detail_panel() are unit-tested
   against the documented DOM catalog shapes (see poker-tooling skill
   references/evenbet-tournament-dom-catalog.md).

Results (winners/payouts): not exposed by the lobby -> results() returns
None (documented limitation).
Hand data: not exposed without a live table session -> hand_data() returns [].
Snapshots: per-tournament detail is only available while a browser session is
attached; snapshot() returns the last fetched detail when present, else None.

Identity: canonical (site, site_tournament_id). The real EvenBet tournament
id comes from the detail panel (#8599 -> "8599"). When absent, the
normalizer derives a stable name-hash id.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from ..adapters import SiteAdapter
from ..normalize import parse_evenbet_buyin, clean_int, clean_money, normalize_game_type

log = logging.getLogger("mtt.sunbet")

SA = ZoneInfo("Africa/Johannesburg")

LOBBY_URL = "https://sb-play.pkrsrv.com/d/?tournaments/all&lang=en"

# EvenBet status badge text -> canonical status.
SB_STATUS_MAP = {
    "registering": "registration",
    "late registration": "late_reg",
    "running": "running",
    "completed": "completed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "finished": "completed",
    "scheduled": "scheduled",
    "postponed": "scheduled",
}


def _status(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    if "register" in s:
        return "registration"
    if "late" in s:
        return "late_reg"
    if "complete" in s or "finish" in s or "end" in s:
        return "completed"
    if "cancel" in s:
        return "cancelled"
    if "run" in s or "play" in s or "start" in s:
        return "running"
    return SB_STATUS_MAP.get(s)


MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def _parse_start(v) -> Optional[str]:
    """'Jul 07, 09:00' -> UTC ISO (year assumed from SAST now)."""
    if not v:
        return None
    s = str(v).strip()
    m = re.match(r"^([A-Za-z]{3}) (\d{1,2}), (\d{1,2}):(\d{2})$", s)
    if not m:
        return None
    month = MONTHS.get(m.group(1))
    if not month:
        return None
    now = datetime.now(SA)
    try:
        dt = datetime(now.year, month, int(m.group(2)),
                      int(m.group(3)), int(m.group(4)), tzinfo=SA)
    except ValueError:
        return None
    # schedule times are always in the future/current window; if the parsed
    # month/day is already far past, roll to next year (Dec->Jan schedules)
    if dt < now - timedelta(days=1):
        try:
            dt = dt.replace(year=dt.year + 1)
        except ValueError:  # Feb 29 edge
            return None
    return dt.astimezone(timezone.utc).isoformat()


def _total_entry_cost(buyin, fee, bounty) -> Optional[int]:
    parts = [p for p in (buyin, fee, bounty) if p is not None]
    return sum(parts) if parts else None


def parse_lobby_rows(rows) -> list:
    """EvenBet lobby rows (catalog shape) -> canonical-ish tournament dicts.

    Each row: {start, status, name, game, buyIn, prize, players, action}.
    """
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue
        buyin, fee, bounty = parse_evenbet_buyin(r.get("buyIn"))
        t = {
            "site": "sunbet",
            "site_tournament_id": None,   # filled from detail panel when present
            "name": name,
            "game_type": normalize_game_type(r.get("game")),
            "format": "MTT",
            "currency": "ZAR",
            "buyin": buyin,
            "fee": fee,
            "total_entry_cost": _total_entry_cost(buyin, fee, bounty),
            "guarantee": None,
            "start_time": _parse_start(r.get("start")),
            "status": _status(r.get("status") or r.get("action")),
            "entries": clean_int(r.get("players")),
            "prize_pool": clean_money(r.get("prize")),
            "source": "lobby",
        }
        if t["status"] is None:
            # action button "COMPLETED" carries the status for finished rows
            t["status"] = _status(r.get("action"))
        out.append(t)
    return out


def parse_detail_panel(detail: dict) -> dict:
    """Detail panel fields -> canonical-ish overrides (id wins over row).

    Detail shape (catalog): {id: "#8599", fullName, gameType, statusBadge,
    startsIn, registration, totalPrizePool, guaranteed, buyInDetail, ...}.
    """
    if not isinstance(detail, dict):
        return {}
    out = {}
    tid = (detail.get("id") or "").strip().lstrip("#")
    if tid:
        out["site_tournament_id"] = tid
    if detail.get("fullName"):
        out["name"] = str(detail["fullName"]).strip()
    if detail.get("gameType"):
        out["game_type"] = normalize_game_type(detail.get("gameType"))
    if detail.get("statusBadge"):
        out["status"] = _status(detail.get("statusBadge"))
    if detail.get("totalPrizePool"):
        pool = clean_money(detail.get("totalPrizePool"))
        if pool is not None:
            out["prize_pool"] = pool
    if detail.get("guaranteed"):
        g = clean_money(detail.get("guaranteed"))
        if g is not None:
            out["guarantee"] = g
    if detail.get("buyInDetail"):
        buyin, fee, bounty = parse_evenbet_buyin(detail.get("buyInDetail"))
        out["buyin"] = buyin
        out["fee"] = fee
        out["total_entry_cost"] = _total_entry_cost(buyin, fee, bounty)
    if detail.get("players") is not None:
        n = clean_int(detail.get("players"))
        if n is not None:
            out["entries"] = n
    return out


def merge_row_detail(row: dict, detail: dict) -> dict:
    """Row first, detail overrides (detail has the real id + rich fields)."""
    merged = dict(row)
    merged.update({k: v for k, v in detail.items() if v is not None})
    if merged.get("site_tournament_id") is None:
        merged.pop("site_tournament_id", None)  # let normalizer name-hash
    return merged


def parse_file_payload(payload) -> list:
    """Accept {rows:[...], details:{...}} | bare row list | {tournaments:[...]}."""
    if isinstance(payload, dict) and "tournaments" in payload:
        return list(payload["tournaments"])  # already canonical-shaped
    if isinstance(payload, dict) and "rows" in payload:
        rows = payload.get("rows") or []
        details = payload.get("details") or {}
        parsed = []
        for r in parse_lobby_rows(rows):
            detail = parse_detail_panel(details.get(r.get("name") or r.get("site_tournament_id")) or {})
            parsed.append(merge_row_detail(r, detail))
        return parsed
    if isinstance(payload, list):
        return parse_lobby_rows(payload)
    return []


class SunBetAdapter(SiteAdapter):
    """Canonical interface over EvenBet tournament lobby.

    Modes:
      browser=True -> attempt Selenium collection (needs cookies/session)
      input_dir   -> read EvenBet-shaped JSON payloads from a directory
    """

    site = "sunbet"

    def __init__(self, browser: bool = False, input_dir: Optional[str] = None,
                 driver=None, collect_timeout_s: float = 90.0):
        self.browser = browser
        self.input_dir = input_dir or os.environ.get("MTT_SB_INPUT")
        self.driver = driver
        self.collect_timeout_s = collect_timeout_s
        self.last_error: Optional[str] = None
        self._last_detail: dict = {}   # ref -> last detail panel seen

    # ---------------- canonical interface ----------------

    def discover(self) -> list:
        payloads = self._collect()
        out = []
        for p in payloads:
            out.extend(parse_file_payload(p))
        # de-dupe by site_tournament_id / name (detail rows win)
        by_key: dict = {}
        for t in out:
            key = t.get("site_tournament_id") or t.get("name")
            if not key:
                continue
            by_key[key] = t
        return list(by_key.values())

    def snapshot(self, ref: str) -> Optional[dict]:
        detail = self._last_detail.get(ref)
        if not detail:
            return None
        return {
            "captured_at": datetime.now().astimezone().isoformat(),
            "status": _status(detail.get("statusBadge")),
            "entries": clean_int(detail.get("players")),
            "prize_pool": clean_money(detail.get("totalPrizePool")),
            "small_blind": None, "big_blind": None, "ante": None,
            "average_stack": None, "tables_active": None, "current_level": None,
            "late_registration": None,
        }

    def results(self, ref: str) -> Optional[dict]:
        # EvenBet lobby does not expose winners/payouts (documented limitation)
        return None

    def hand_data(self, ref: str) -> list:
        # Not exposed without a live table session (documented limitation)
        return []

    # ---------------- collection ----------------

    def _collect(self) -> list:
        payloads = []
        if self.input_dir:
            payloads.extend(self._collect_files())
        if self.browser:
            payloads.extend(self._collect_browser())
        if not payloads and not self.input_dir and not self.browser:
            self.last_error = ("no collection source configured: pass "
                               "browser=True and/or input_dir= (env MTT_SB_INPUT)")
        return payloads

    def _collect_files(self) -> list:
        if not self.input_dir:
            return []
        d = Path(self.input_dir)
        if not d.is_dir():
            self.last_error = f"input dir not found: {self.input_dir}"
            return []
        done = d / "processed"
        done.mkdir(parents=True, exist_ok=True)
        out = []
        for f in sorted(d.glob("*.json")):
            try:
                payload = json.loads(f.read_text())
            except (OSError, ValueError) as e:
                log.warning("unreadable input file %s: %s", f, e)
                continue
            out.append(payload)
            os.replace(f, done / f.name)
        return out

    def _collect_browser(self) -> list:
        try:
            collector = SunBetBrowserCollector(self.driver, self.collect_timeout_s)
            payload = collector.collect()
        except Exception as e:
            self.last_error = f"browser collection failed: {e}"
            log.warning("SunBet browser collection failed: %s", e)
            return []
        if not payload.get("rows"):
            self.last_error = "browser collection returned no tournament rows"
            return []
        return [payload]


class SunBetBrowserCollector:
    """Selenium collector for the EvenBet tournament lobby.

    Requires a session with SunBet cookies (inject from the user's Chrome
    profile — see poker-tooling skill: evenbet-cookie-injection.md).
    """

    def __init__(self, driver=None, timeout_s: float = 90.0):
        self.driver = driver
        self.timeout_s = timeout_s
        self._owns_driver = driver is None

    def _get_driver(self):
        if self.driver is not None:
            return self.driver
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1600,1200")
        return webdriver.Chrome(options=opts)

    def collect(self) -> dict:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        driver = self._get_driver()
        try:
            driver.set_page_load_timeout(45)
            driver.get(LOBBY_URL)
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                                                ".Table__body_row_table")))
            rows = self._scroll_rows(driver)
            details = {}
            for r in rows:
                detail = self._read_detail(driver, r)
                if detail:
                    details[detail.get("id") or r.get("name")] = detail
            return {"rows": rows, "details": details}
        finally:
            if self._owns_driver:
                driver.quit()

    def _scroll_rows(self, driver) -> list:
        """Virtual scrolling: keep scrolling until the row count stabilizes."""
        from selenium.webdriver.common.by import By
        out = []
        last_count = -1
        for _ in range(25):
            out = self._extract_rows(driver)
            if len(out) == last_count:
                break
            last_count = len(out)
            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.2)
        return out

    def _extract_rows(self, driver) -> list:
        from selenium.webdriver.common.by import By

        def txt(el, sel):
            try:
                e = el.find_element(By.CSS_SELECTOR, sel)
                return (e.text or "").strip()
            except Exception:
                return ""

        rows = driver.find_elements(By.CSS_SELECTOR,
                                    ".Table__body_row_table:not(.hidden):not(.skeletonRow)")
        out = []
        for r in rows:
            name = txt(r, ".trct-name .Table__body_item_text")
            if not name:
                continue
            out.append({
                "start": txt(r, ".trct-status-group-time-start .Table__body_item_text"),
                "status": txt(r, ".trct-status .Table__body_item_text"),
                "name": name,
                "game": txt(r, ".trct-game-type .Table__body_item_text"),
                "buyIn": txt(r, ".trct-buy-in .Table__body_item_text"),
                "prize": txt(r, ".trct-prize .Table__body_item_text"),
                "players": txt(r, ".trct-num-players .Table__body_item_text"),
                "action": txt(r, ".tas-register .SimpleButton__text"),
            })
        return out

    def _read_detail(self, driver, row) -> Optional[dict]:
        from selenium.webdriver.common.by import By

        def txt(el, sel):
            try:
                e = el.find_element(By.CSS_SELECTOR, sel)
                return (e.text or "").strip()
            except Exception:
                return ""

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
                row)
            time.sleep(1.8)
            panels = driver.find_elements(
                By.CSS_SELECTOR, ".right_content .LobbyTournamentsMenuContainer")
            if not panels:
                panels = driver.find_elements(By.CSS_SELECTOR,
                                              ".LobbyTournamentsMenuContainer")
            if not panels:
                return None
            p = panels[0]
            return {
                "id": txt(p, ".LobbyTournamentsMenuContainer__info__tournament_id"),
                "fullName": txt(p, ".LobbyTournamentsMenuContainer__info__tournament_name"),
                "gameType": txt(p, ".LobbyTournamentsMenuContainer__game_type"),
                "statusBadge": txt(p, ".LobbyTournamentsMenuContainer__info__status_badge .text"),
                "startsIn": txt(p, ".start-time-left span"),
                "registration": txt(p, ".registration-date span"),
                "totalPrizePool": txt(p, ".total-prize-pool span"),
                "guaranteed": txt(p, ".guaranteed-prize span"),
                "buyInDetail": txt(p, ".buy-in span"),
                "players": txt(p, ".LobbyTournamentsMenuContainer__fields .players-count span"),
            }
        except Exception as e:
            log.debug("detail panel read failed: %s", e)
            return None
