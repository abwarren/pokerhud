"""PokerBet adapter — BetConstruct/SkillGames platform.

Sources (verified 2026-08-10):
1. CMS promotions REST (auth-free, live-verified):
   GET https://go-cms.pokerbet.co.za/api/public/v1/eng/partners/18751019/promotions
   ?use_webp=1&platform=0&category=poker
   -> {"code","text","success","data":[{title,content,id,...}]}
   Only flagship/promoted tournaments appear here (small set, buy-in + GTD
   embedded in content text, e.g. "buy-in of R700+R70 ... R250,000").

2. WS live lobby (token-gated):
   wss://poker-general.skillgames-bc.com  JSON protocol
   {"cmd":"getTournaments"} etc. Returns the FULL schedule with live
   entries/status. Tokens go stale (session-specific); when stale the
   adapter degrades to CMS-only and logs a PARSER_ERROR so the gap is
   visible in ingestion_runs/parser_errors.

Results (winners/payouts): NOT exposed by these endpoints -> results()
returns None (documented limitation; see recon spec).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import requests

from ..adapters import SiteAdapter

log = logging.getLogger("mtt.pokerbet")

PARTNER_ID = os.environ.get("MTT_PB_PARTNER", "18751019")
CMS_BASE = os.environ.get("MTT_PB_CMS", "https://go-cms.pokerbet.co.za")
WS_URL = os.environ.get("MTT_PB_WS", "wss://poker-general.skillgames-bc.com")
WS_TIMEOUT_S = float(os.environ.get("MTT_PB_WS_TIMEOUT", "12"))

# Auth tokens are session-specific (from a browser network trace) and must
# come from the environment — never hardcoded. When unset the adapter
# degrades to CMS-only and logs the gap (ws_stale=True).

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/146.0",
}

NON_POKER_INDICATORS = ("casino", "sport", "slots", "live casino", "roulette",
                        "blackjack", "baccarat", "craps", "jackpot", "bingo",
                        "ts&cs", "terms and conditions", "terms & conditions",
                        "terms and cond", "rakeback", "rake back",
                        "refer a friend", "sponsorship", "welcome offer")
POKER_TITLE_KEYWORDS = ("poker", "hold", "omaha", "mtt", "gt d", "gtd", "slam",
                        "turbo", "freeze", "bounty", "satellite", "deep", "rebuy",
                        "add-on", "high roller", "bubble")


def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s or "")


def parse_zar_amount(s: str) -> Optional[int]:
    m = re.search(r"R\s?([\d, ]+)", s, re.I)
    if not m:
        return None
    digits = re.sub(r"[^\d]", "", m.group(1))
    return int(digits) if digits else None


class PokerBetAdapter(SiteAdapter):
    site = "pokerbet"

    def __init__(self, session: Optional[requests.Session] = None,
                 use_ws: bool = True):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self.use_ws = use_ws
        self.client_id = os.environ.get("MTT_PB_CLIENT_ID")
        self.token = os.environ.get("MTT_PB_TOKEN")
        self._ws_tournaments: dict = {}   # ref -> last live dict
        self.ws_stale = False

    # ---------------- sources ----------------

    def _cms_promotions(self) -> list:
        url = f"{CMS_BASE}/api/public/v1/eng/partners/{PARTNER_ID}/promotions"
        r = self.session.get(url, params={"use_webp": "1", "platform": "0",
                                          "category": "poker"}, timeout=20)
        r.raise_for_status()
        data = r.json()
        items = data.get("data", []) if isinstance(data, dict) else []
        return [i for i in items if isinstance(i, dict)]

    def _ws_live(self) -> list:
        """Full live schedule via WS. Returns list of raw tournament dicts."""
        if not self.use_ws:
            return []
        try:
            return asyncio.run(self._ws_collect())
        except Exception as e:
            log.warning("WS live lobby failed: %s", e)
            return []

    async def _ws_collect(self) -> list:
        if not self.token or not self.client_id:
            log.warning("MTT_PB_TOKEN/MTT_PB_CLIENT_ID not set — CMS-only mode")
            return []
        import websockets
        out: list = []
        headers = {"Origin": "https://poker-web.pokerbet.co.za"}
        try:  # websockets >= 12
            ws = await websockets.connect(WS_URL, open_timeout=8,
                                          additional_headers=headers)
        except TypeError:  # websockets < 12
            ws = await websockets.connect(WS_URL, open_timeout=8,
                                          extra_headers=headers)
        async with ws:
            # login shape verified against the working scraper
            # (table_scraper.py:568-576) — flat cmd/login, not nested auth
            player_id = os.environ.get("MTT_PB_PLAYER_ID", "0")
            msgs = [
                {"cmd": "login", "partnerId": int(PARTNER_ID),
                 "clientId": int(self.client_id), "token": self.token,
                 "playerId": int(player_id)},
                {"cmd": "getLobby", "productId": 3},
                {"cmd": "getTournaments", "partnerId": int(PARTNER_ID)},
                {"cmd": "subscribe", "channel": "tournaments",
                 "partnerId": int(PARTNER_ID)},
            ]
            for m in msgs:
                await ws.send(json.dumps(m))
                await asyncio.sleep(0.4)
            # collect up to WS_TIMEOUT_S
            loop_end = asyncio.get_event_loop().time() + WS_TIMEOUT_S
            while asyncio.get_event_loop().time() < loop_end:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2)
                except asyncio.TimeoutError:
                    continue
                parsed = self._parse_ws_message(raw)
                if parsed:
                    out.append(parsed)
        return out

    def _parse_ws_message(self, raw) -> Optional[dict]:
        """Parse one WS frame; returns a canonical-ish tournament dict or None."""
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return None
        if not isinstance(msg, dict):
            return None
        if msg.get("cmd") == "tournaments" or "tournaments" in msg:
            for t in msg.get("data", msg.get("tournaments", [])) or []:
                if isinstance(t, dict):
                    self._ws_tournaments[str(t.get("id"))] = t
            return msg
        if isinstance(msg.get("data"), list):
            for t in msg["data"]:
                if isinstance(t, dict) and t.get("buyIn") is not None:
                    self._ws_tournaments[str(t.get("id"))] = t
        return None

    # ---------------- canonical interface ----------------

    def discover(self) -> list:
        discovered = []

        # 1) CMS promotions — always (auth-free)
        try:
            for item in self._cms_promotions():
                t = self._cms_to_tournament(item)
                if t:
                    discovered.append(t)
        except Exception as e:
            log.warning("CMS scrape failed: %s", e)

        # 2) WS live lobby — full schedule when tokens valid
        if self.token and self.client_id:
            self._ws_live()
            if self._ws_tournaments:
                for ref, t in self._ws_tournaments.items():
                    discovered.append(self._ws_to_tournament(ref, t))
            elif self.use_ws:
                self.ws_stale = True
        else:
            self.ws_stale = True

        # de-dupe by site_tournament_id (WS wins: has live fields)
        by_ref: dict = {}
        for t in discovered:
            by_ref[t["site_tournament_id"]] = t
        return list(by_ref.values())

    def snapshot(self, ref: str) -> Optional[dict]:
        live = self._ws_tournaments.get(ref)
        if not live:
            return None
        return {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "status": self._ws_status(live),
            "entries": self._num(live.get("playersRegistered")),
            "players_remaining": self._num(live.get("playersRemaining")),
            "tables_active": self._num(live.get("tablesActive")),
            "prize_pool": self._num(live.get("prizePool")) or self._num(live.get("prizePoolAmount")),
            "current_level": self._num(live.get("currentLevel")),
            "small_blind": self._num(live.get("smallBlind")),
            "big_blind": self._num(live.get("bigBlind")),
            "ante": self._num(live.get("ante")),
            "average_stack": self._num(live.get("averageStack")),
            "late_registration": bool(live.get("lateRegistration")),
        }

    def results(self, ref: str) -> Optional[dict]:
        # Not exposed by CMS/WS endpoints (documented limitation)
        return None

    def hand_data(self, ref: str) -> list:
        """Hand histories via MTT_PB_HANDS_URL when a verified endpoint is
        configured; otherwise none (documented limitation)."""
        url = os.environ.get("MTT_PB_HANDS_URL")
        if not url or not self.token:
            return []
        try:
            r = self.session.get(
                f"{url.rstrip('/')}/tournament/{ref}/hands",
                params={"token": self.token, "limit": 100}, timeout=15)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and isinstance(data.get("hands"), list):
                return data["hands"]
            if isinstance(data, list):
                return data
            log.warning("unexpected hands response shape for %s", ref)
            return []
        except Exception as e:
            log.warning("hands fetch failed for %s: %s", ref, e)
            return []

    # ---------------- parsing helpers ----------------

    def _cms_to_tournament(self, item: dict) -> Optional[dict]:
        title = (item.get("title") or "").strip()
        content = strip_html(item.get("content") or "")
        if not title:
            return None
        low = f"{title} {content}".lower()
        if any(i in low for i in NON_POKER_INDICATORS):
            return None
        if not any(k in low for k in POKER_TITLE_KEYWORDS):
            return None

        t = {
            "site": "pokerbet",
            "site_tournament_id": f"cms-{item.get('id')}",
            "name": title,
            "game_type": None,
            "format": "MTT",
            "currency": "ZAR",
            "start_time": None,
            "status": "scheduled",
            "source": "cms",
            "buyin": None,
            "fee": None,
            "total_entry_cost": None,
            "guarantee": None,
        }
        # buy-in patterns: 'R700+R70', 'R700 + R70', 'buy-in of R700 + R70',
        # 'R250+R25', or a bare 'R1,000' entry cost.
        m = re.search(r"R\s?([\d][\d ]*)\s*\+\s*R\s?([\d][\d ]*)", content, re.I)
        if m:
            t["buyin"] = int(re.sub(r"[^\d]", "", m.group(1)))
            t["fee"] = int(re.sub(r"[^\d]", "", m.group(2)))
            t["total_entry_cost"] = t["buyin"] + t["fee"]
        else:
            m1 = re.search(r"(?:buy-in|buyin|entry)\s*(?:of|:)?\s*R\s?([\d][\d ,]*)",
                           low, re.I)
            if m1:
                t["buyin"] = parse_zar_amount(m1.group(0))
                t["total_entry_cost"] = t["buyin"]
        # guarantee: keyword + bounded gap, CONTENT only — the title often
        # carries its own 'R200k Guaranteed' text and must not hijack the match
        # keyword is case-insensitive; gap excludes capital R (lowercase 'r'
        # like "prize" is fine); amount may be written with either case
        g = re.search(r"(?i:guarantee|guaranteed|gtd)\b[^R]{0,60}?[Rr]\s?([\d, ]+)",
                      content)
        if g:
            t["guarantee"] = parse_zar_amount(g.group(0))
        if t["guarantee"] is None:
            # title pattern fallback: 'R125k GTD' / 'R250k Guaranteed'
            g2 = re.search(r"R\s?([\d.]+)\s*([km])\b", title.lower())
            if g2 and ("gtd" in title.lower() or "guarantee" in title.lower()):
                mult = 1_000_000 if g2.group(2) == "m" else 1_000
                t["guarantee"] = int(float(g2.group(1)) * mult)
        tm = re.search(r"(\d{1,2})[:\\\\.](\d{2})\s*(am|pm)", low)
        if tm:
            # CMS promo pages carry time-of-day without a date — store the raw
            # hint (rides in raw_events); canonical start_time stays None and
            # the quality engine flags it as missing. Never guess a date.
            t["start_time_raw"] = f"{int(tm.group(1)):02d}:{tm.group(2)} {tm.group(3)}"
        if "satellite" in low:
            t["format"] = "SATELLITE"
        if "omaha" in low or "plo" in low:
            t["game_type"] = "PLO"
        elif "hold" in low or "nlhe" in low or "no limit" in low:
            t["game_type"] = "NLHE"
        return t

    def _ws_to_tournament(self, ref: str, t: dict) -> dict:
        name = (t.get("name") or t.get("title") or f"tournament-{ref}").strip()
        buyin = t.get("buyIn") if isinstance(t.get("buyIn"), (int, float)) else None
        return {
            "site": "pokerbet",
            "site_tournament_id": ref,
            "name": name,
            "game_type": self._game_type(name),
            "format": "MTT",
            "currency": "ZAR",
            "buyin": buyin,
            "fee": t.get("fee") if isinstance(t.get("fee"), (int, float)) else None,
            "total_entry_cost": buyin + t["fee"] if buyin is not None and t.get("fee") else None,
            "guarantee": self._num(t.get("guarantee")) or self._num(t.get("prizePoolGuaranteed")),
            "start_time": self._num(t.get("startTime")) or t.get("startTime"),
            "status": self._ws_status(t),
            "entries": self._num(t.get("playersRegistered")),
            "reentries": self._num(t.get("reentries")),
            "prize_pool": self._num(t.get("prizePool")) or self._num(t.get("prizePoolAmount")),
            "max_players": self._num(t.get("maxPlayers")),
            "source": "ws",
        }

    @staticmethod
    def _num(v) -> Optional[int]:
        if v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _game_type(name: str) -> Optional[str]:
        low = name.lower()
        if "omaha" in low or "plo" in low:
            return "PLO"
        if "hold" in low:
            return "NLHE"
        return None

    @staticmethod
    def _ws_status(t: dict) -> str:
        s = str(t.get("status", "")).lower()
        if "registr" in s:
            return "registration"
        if "late" in s:
            return "late_reg"
        if "finish" in s or "end" in s or "complete" in s:
            return "completed"
        if "cancel" in s:
            return "cancelled"
        if "start" in s or "run" in s or "play" in s:
            return "running"
        return "scheduled" if not s else s
