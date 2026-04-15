#!/usr/bin/env python3
"""
PokerBet Tournament Scraper
============================
Connects to BetConstruct's poker backend via WebSocket and REST APIs
to scrape all tournament data from pokerbet.co.za.

BetConstruct Architecture (from network trace):
  - WebSocket: wss://poker-general.skillgames-bc.com (live lobby data)
  - Gateway:   https://sg-api.skillgames-bc.com/ (REST)
  - CMS:       https://go-cms.pokerbet.co.za/ (promotions, banners)
  - Hands:     https://poker-hands.skillgames-bc.com (hand history)
  - Promos:    https://poker-promotions.skillgames-bc.com (bonuses)
  - Rates:     https://poker-rate.skillgames-bc.com/api/rate
  - Partner:   18751019
  - Product:   3 (poker)
  - Package:   4349

Usage:
  python3 tournament_scraper.py              # Run full scrape
  python3 tournament_scraper.py --ws-only    # WebSocket discovery only
  python3 tournament_scraper.py --rest-only  # REST API scrape only
  python3 tournament_scraper.py --discover   # Protocol discovery mode
"""

import asyncio
import json
import time
import sys
import os
import logging
from datetime import datetime
from pathlib import Path

import requests
import websockets

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PARTNER_ID = "18751019"
PRODUCT_ID = "3"       # poker
PACKAGE_ID = "4349"

# Auth from network trace (session-specific, may need refresh)
CLIENT_ID = "92311469"
CLIENT_ID_HASH = "8d96fa1aae7d4c613ab396f3677ee1e9a9bb4d75c233156a80774a462fa84a09"
PLAYER_ID = "357652843"
TOKEN = "2F90D07AC6E160842CFC8757484A5857"

# Endpoints
WS_URL = "wss://poker-general.skillgames-bc.com"
CMS_BASE = "https://go-cms.pokerbet.co.za"
PROMO_BASE = "https://poker-promotions.skillgames-bc.com"
GATEWAY_BASE = "https://sg-api.skillgames-bc.com"
HANDS_BASE = "https://poker-hands.skillgames-bc.com"
RATES_BASE = "https://poker-rate.skillgames-bc.com"

# Output
OUTPUT_DIR = Path("/opt/pokerhud/tournament_data")
OUTPUT_DIR.mkdir(exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(OUTPUT_DIR / "scraper.log")
    ]
)
log = logging.getLogger("tournament_scraper")

# Headers mimicking the browser from network trace
BROWSER_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
}

AUTH_HEADERS = {
    **BROWSER_HEADERS,
    "client_id": CLIENT_ID,
    "client_id_hash": CLIENT_ID_HASH,
}


# ---------------------------------------------------------------------------
# REST API Scraping
# ---------------------------------------------------------------------------
class RestScraper:
    """Scrapes tournament data from BetConstruct REST APIs."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)
        self.results = {}

    def scrape_all(self):
        log.info("=" * 60)
        log.info("REST API SCRAPE - PokerBet Tournament Data")
        log.info("=" * 60)

        self.scrape_promotions()
        self.scrape_banners()
        self.scrape_games()
        self.scrape_bonuses()
        self.scrape_rates()
        self.scrape_config()
        self.scrape_notes()

        return self.results

    def scrape_promotions(self):
        """Fetch poker promotions (includes tournament schedules)."""
        log.info("[REST] Fetching poker promotions...")
        url = f"{CMS_BASE}/api/public/v1/eng/partners/{PARTNER_ID}/promotions"
        params = {
            "use_webp": "1",
            "platform": "0",
            "category": "poker",
            "with_meta": "1",
            "country": "ZA"
        }
        try:
            r = self.session.get(url, params=params, timeout=15)
            data = r.json()
            self.results["promotions"] = data
            log.info(f"  -> Got {len(data) if isinstance(data, list) else 'response'} promotions")
            self._save("promotions.json", data)
        except Exception as e:
            log.error(f"  -> Failed: {e}")
            self.results["promotions"] = {"error": str(e)}

    def scrape_banners(self):
        """Fetch poker banners (tournament promo images)."""
        log.info("[REST] Fetching poker banners...")
        url = f"{CMS_BASE}/api/public/v1/eng/partners/{PARTNER_ID}/components/poker_banners/contents"
        params = {"use_webp": "1", "platform": "0", "country": "ZA"}
        try:
            r = self.session.get(url, params=params, timeout=15)
            data = r.json()
            self.results["banners"] = data
            log.info(f"  -> Got banners response")
            self._save("banners.json", data)
        except Exception as e:
            log.error(f"  -> Failed: {e}")

    def scrape_games(self):
        """Fetch game catalog."""
        log.info("[REST] Fetching game catalog...")
        url = f"{CMS_BASE}/casino/getGames"
        params = {
            "partner_id": PARTNER_ID,
            "lang": "eng",
            "external_id": "28",
            "is_mobile": "0",
            "country": "ZA"
        }
        try:
            r = self.session.get(url, params=params, timeout=15)
            data = r.json()
            self.results["games"] = data
            game_count = len(data.get("games", []))
            log.info(f"  -> Got {game_count} games")
            self._save("games.json", data)
        except Exception as e:
            log.error(f"  -> Failed: {e}")

    def scrape_bonuses(self):
        """Fetch poker bonuses (type 1 = regular, type 3 = tournament tickets)."""
        for bonus_type in [1, 2, 3, 4, 5]:
            log.info(f"[REST] Fetching bonuses type={bonus_type}...")
            url = f"{PROMO_BASE}/bonuses/product/{PRODUCT_ID}/partner/{PARTNER_ID}"
            params = {"type": str(bonus_type)}
            headers = {**AUTH_HEADERS, "Referer": "https://poker-web.pokerbet.co.za/"}
            try:
                r = self.session.get(url, params=params, headers=headers, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    self.results[f"bonuses_type_{bonus_type}"] = data
                    log.info(f"  -> Got bonuses type {bonus_type}: {len(data) if isinstance(data, list) else 'response'}")
                    self._save(f"bonuses_type_{bonus_type}.json", data)
                else:
                    log.warning(f"  -> HTTP {r.status_code}")
                    self.results[f"bonuses_type_{bonus_type}"] = {"status": r.status_code}
            except Exception as e:
                log.error(f"  -> Failed: {e}")

    def scrape_rates(self):
        """Fetch currency rates (ZAR/EUR)."""
        log.info("[REST] Fetching currency rates...")
        url = f"{RATES_BASE}/api/rate"
        try:
            r = self.session.post(url, json={"mainCurrency": "ZAR", "rates": ["EUR", "ZAR"]},
                                  headers={**BROWSER_HEADERS, "Referer": "https://poker-web.pokerbet.co.za/"},
                                  timeout=15)
            data = r.json()
            self.results["rates"] = data
            log.info(f"  -> Rates: {data}")
            self._save("rates.json", data)
        except Exception as e:
            log.error(f"  -> Failed: {e}")

    def scrape_config(self):
        """Fetch poker client config."""
        log.info("[REST] Fetching poker client config...")
        url = f"https://poker-web.pokerbet.co.za/{PARTNER_ID}/config.json"
        try:
            r = self.session.get(url, timeout=15)
            data = r.json()
            self.results["config"] = data
            log.info(f"  -> Config keys: {list(data.keys())}")
            self._save("config.json", data)
        except Exception as e:
            log.error(f"  -> Failed: {e}")

    def scrape_notes(self):
        """Fetch player notes (requires auth)."""
        log.info("[REST] Fetching player notes...")
        url = f"{GATEWAY_BASE}/Notes/"
        params = {"PlayerId": PLAYER_ID, "ClientId": CLIENT_ID, "format": "json"}
        try:
            r = self.session.get(url, params=params, timeout=15)
            if r.status_code == 200:
                data = r.json()
                self.results["notes"] = data
                log.info(f"  -> Got notes")
                self._save("notes.json", data)
            else:
                log.warning(f"  -> HTTP {r.status_code}")
        except Exception as e:
            log.error(f"  -> Failed: {e}")

    def _save(self, filename, data):
        path = OUTPUT_DIR / filename
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        log.info(f"  -> Saved to {path}")


# ---------------------------------------------------------------------------
# WebSocket Scraping - BetConstruct Protocol Discovery
# ---------------------------------------------------------------------------
class WebSocketScraper:
    """
    Connects to BetConstruct's WebSocket to scrape live tournament lobby data.

    BetConstruct Skillgames uses a custom WebSocket protocol. This scraper
    tries multiple message formats to discover the correct protocol and
    extract tournament listings.
    """

    def __init__(self):
        self.messages_received = []
        self.tournaments = []

    async def scrape(self, discover_mode=False):
        log.info("=" * 60)
        log.info("WEBSOCKET SCRAPE - BetConstruct Live Tournament Data")
        log.info("=" * 60)
        log.info(f"Connecting to {WS_URL}...")

        # BetConstruct WebSocket connection with browser-like headers
        extra_headers = {
            "Origin": "https://poker-web.pokerbet.co.za",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.7680.164 Safari/537.36",
        }

        try:
            async with websockets.connect(
                WS_URL,
                additional_headers=extra_headers,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                log.info("  -> Connected!")

                if discover_mode:
                    await self._discover_protocol(ws)
                else:
                    await self._scrape_tournaments(ws)

        except websockets.exceptions.InvalidStatusCode as e:
            log.error(f"  -> Connection rejected: {e}")
            log.info("  -> Trying alternate WebSocket URLs...")
            await self._try_alternate_urls()
        except Exception as e:
            log.error(f"  -> WebSocket error: {type(e).__name__}: {e}")

        return self.tournaments

    async def _scrape_tournaments(self, ws):
        """Send auth + lobby subscription, collect tournament data."""

        # Phase 1: Authenticate
        auth_messages = self._get_auth_messages()
        for msg in auth_messages:
            log.info(f"  -> Sending: {json.dumps(msg)[:200]}...")
            await ws.send(json.dumps(msg))
            await asyncio.sleep(0.5)

        # Phase 2: Subscribe to tournament lobby
        lobby_messages = self._get_lobby_messages()
        for msg in lobby_messages:
            log.info(f"  -> Sending: {json.dumps(msg)[:200]}...")
            await ws.send(json.dumps(msg))
            await asyncio.sleep(0.3)

        # Phase 3: Collect responses
        log.info("  -> Listening for tournament data (30s)...")
        await self._collect_messages(ws, duration=30)

        # Save all received messages
        self._save_messages()

    async def _discover_protocol(self, ws):
        """Send various message formats to discover the correct protocol."""
        log.info("  -> DISCOVERY MODE: Probing WebSocket protocol...")

        # Try receiving any initial messages from server
        log.info("  -> Waiting for server greeting (5s)...")
        await self._collect_messages(ws, duration=5)

        # Try different authentication formats
        probe_messages = [
            # BetConstruct standard format
            {"cmd": "login", "partnerId": PARTNER_ID, "clientId": CLIENT_ID, "token": TOKEN},

            # JSON-RPC style
            {"jsonrpc": "2.0", "method": "login", "params": {"partnerId": PARTNER_ID, "token": TOKEN}, "id": 1},

            # Flat auth
            {"action": "auth", "partner_id": PARTNER_ID, "client_id": CLIENT_ID, "token": TOKEN, "player_id": PLAYER_ID},

            # Skillgames format
            {"type": "auth", "data": {"partnerId": int(PARTNER_ID), "clientId": int(CLIENT_ID), "token": TOKEN}},

            # Subscribe without auth
            {"cmd": "getLobby"},
            {"cmd": "getTournaments"},
            {"cmd": "subscribe", "channel": "lobby"},
            {"action": "lobby", "type": "tournaments"},

            # Array format
            [1, "login", {"partnerId": PARTNER_ID, "token": TOKEN}],

            # Numbered command
            {"rid": "1", "command": "get_tournaments", "params": {"partner_id": int(PARTNER_ID)}},

            # Spring platform style
            {"command": "request_session", "params": {"site_id": int(PARTNER_ID), "language": "eng"}},
        ]

        for i, msg in enumerate(probe_messages):
            try:
                payload = json.dumps(msg)
                log.info(f"  -> Probe {i+1}/{len(probe_messages)}: {payload[:150]}...")
                await ws.send(payload)
                await asyncio.sleep(1)

                # Collect any responses
                try:
                    while True:
                        response = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        log.info(f"  <- Response to probe {i+1}: {str(response)[:300]}")
                        self.messages_received.append({
                            "probe_index": i + 1,
                            "probe_sent": msg,
                            "response": response if isinstance(response, str) else response.hex(),
                            "timestamp": datetime.now().isoformat()
                        })
                except asyncio.TimeoutError:
                    log.info(f"  <- No response to probe {i+1}")
            except websockets.exceptions.ConnectionClosed:
                log.warning(f"  -> Connection closed after probe {i+1}")
                break
            except Exception as e:
                log.error(f"  -> Probe {i+1} error: {e}")

        self._save_messages()

    async def _collect_messages(self, ws, duration=10):
        """Collect WebSocket messages for a given duration."""
        end_time = time.time() + duration
        count = 0
        while time.time() < end_time:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                count += 1
                if isinstance(msg, bytes):
                    log.info(f"  <- Binary message ({len(msg)} bytes): {msg[:100].hex()}")
                    self.messages_received.append({
                        "type": "binary",
                        "size": len(msg),
                        "hex_preview": msg[:200].hex(),
                        "timestamp": datetime.now().isoformat()
                    })
                else:
                    log.info(f"  <- Text message: {msg[:300]}")
                    self.messages_received.append({
                        "type": "text",
                        "data": msg,
                        "timestamp": datetime.now().isoformat()
                    })

                    # Try to parse tournament data
                    self._parse_tournament_data(msg)
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                log.warning("  -> Connection closed by server")
                break

        log.info(f"  -> Collected {count} messages in {duration}s")

    async def _try_alternate_urls(self):
        """Try alternate WebSocket URLs if the primary fails."""
        alt_urls = [
            f"wss://poker-general.skillgames-bc.com/ws",
            f"wss://poker-general.skillgames-bc.com/socket",
            f"wss://poker-general.skillgames-bc.com/?partnerId={PARTNER_ID}",
            f"wss://poker-general.skillgames-bc.com/{PARTNER_ID}",
            f"wss://sg-api.skillgames-bc.com/ws",
        ]

        extra_headers = {
            "Origin": "https://poker-web.pokerbet.co.za",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        }

        for url in alt_urls:
            try:
                log.info(f"  -> Trying {url}...")
                async with websockets.connect(url, additional_headers=extra_headers,
                                              close_timeout=5) as ws:
                    log.info(f"  -> Connected to {url}!")
                    await self._collect_messages(ws, duration=5)
                    return
            except Exception as e:
                log.info(f"  -> {url}: {type(e).__name__}")

    def _get_auth_messages(self):
        """Authentication message variants for BetConstruct."""
        return [
            {
                "cmd": "login",
                "partnerId": int(PARTNER_ID),
                "clientId": int(CLIENT_ID),
                "token": TOKEN,
                "playerId": int(PLAYER_ID),
            },
        ]

    def _get_lobby_messages(self):
        """Lobby subscription messages to request tournament data."""
        return [
            {"cmd": "getLobby", "productId": int(PRODUCT_ID)},
            {"cmd": "getTournaments", "partnerId": int(PARTNER_ID)},
            {"cmd": "subscribe", "channel": "tournaments", "partnerId": int(PARTNER_ID)},
            {"cmd": "subscribe", "channel": "lobby"},
        ]

    def _parse_tournament_data(self, raw_msg):
        """Try to extract tournament info from a WebSocket message."""
        try:
            data = json.loads(raw_msg)
        except (json.JSONDecodeError, TypeError):
            return

        # Search for tournament-like data structures
        tournaments = self._find_tournaments(data)
        if tournaments:
            self.tournaments.extend(tournaments)
            log.info(f"  -> Found {len(tournaments)} tournaments!")

    def _find_tournaments(self, obj, depth=0):
        """Recursively search for tournament data in a JSON structure."""
        found = []
        if depth > 10:
            return found

        if isinstance(obj, dict):
            # Check if this dict looks like a tournament
            keys = set(obj.keys())
            tournament_keys = {"name", "buyIn", "buyin", "buy_in", "prizePool", "prize_pool",
                              "startTime", "start_time", "status", "type", "players",
                              "entrants", "registeredPlayers", "blind", "level"}
            if len(keys & tournament_keys) >= 2:
                found.append(obj)

            # Also check for tournament list containers
            for key in ["tournaments", "tournamentList", "tournament_list",
                       "mtts", "sit_and_go", "scheduled", "running"]:
                if key in obj:
                    val = obj[key]
                    if isinstance(val, list):
                        found.extend(val)
                    elif isinstance(val, dict):
                        found.extend(self._find_tournaments(val, depth + 1))

            # Recurse into all values
            for v in obj.values():
                found.extend(self._find_tournaments(v, depth + 1))

        elif isinstance(obj, list):
            for item in obj:
                found.extend(self._find_tournaments(item, depth + 1))

        return found

    def _save_messages(self):
        """Save all collected WebSocket messages."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save raw messages
        raw_path = OUTPUT_DIR / f"ws_messages_{ts}.json"
        with open(raw_path, "w") as f:
            json.dump(self.messages_received, f, indent=2, default=str)
        log.info(f"  -> Saved {len(self.messages_received)} WS messages to {raw_path}")

        # Save extracted tournaments
        if self.tournaments:
            tourney_path = OUTPUT_DIR / f"tournaments_{ts}.json"
            with open(tourney_path, "w") as f:
                json.dump(self.tournaments, f, indent=2, default=str)
            log.info(f"  -> Saved {len(self.tournaments)} tournaments to {tourney_path}")


# ---------------------------------------------------------------------------
# Combined Report
# ---------------------------------------------------------------------------
def generate_report(rest_data, ws_tournaments):
    """Generate a combined tournament report."""
    report = {
        "scrape_time": datetime.now().isoformat(),
        "partner": {
            "id": PARTNER_ID,
            "name": "PokerBet",
            "domain": "pokerbet.co.za",
            "currency": "ZAR",
            "platform": "BetConstruct Skillgames"
        },
        "api_endpoints": {
            "websocket": WS_URL,
            "gateway": GATEWAY_BASE,
            "cms": CMS_BASE,
            "promotions": PROMO_BASE,
            "hand_history": HANDS_BASE,
            "rates": RATES_BASE,
        },
        "auth": {
            "client_id": CLIENT_ID,
            "player_id": PLAYER_ID,
            "note": "Token is session-specific and expires"
        },
        "tournament_data": {
            "from_rest": {
                "promotions": rest_data.get("promotions"),
                "bonuses": {k: v for k, v in rest_data.items() if k.startswith("bonuses_")},
            },
            "from_websocket": ws_tournaments,
        },
        "known_tournaments": [
            {
                "name": "Sunday Slam",
                "guarantee": "R200,000",
                "buy_in": "R700+R70",
                "schedule": "Every Sunday at 6:00pm",
                "source": "CMS promotions"
            },
            {
                "name": "Satellite Tournaments",
                "buy_in": "From R22",
                "schedule": "Thursday through Sunday",
                "qualifies_for": "Sunday Slam",
                "source": "CMS promotions"
            }
        ],
        "rates": rest_data.get("rates"),
    }

    path = OUTPUT_DIR / "tournament_report.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info(f"Report saved to {path}")

    # Also save human-readable summary
    summary_path = OUTPUT_DIR / "TOURNAMENT_SUMMARY.txt"
    with open(summary_path, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("POKERBET TOURNAMENT SCRAPE SUMMARY\n")
        f.write(f"Scraped: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")

        f.write("KNOWN TOURNAMENTS:\n")
        f.write("-" * 40 + "\n")
        for t in report["known_tournaments"]:
            f.write(f"  {t['name']}\n")
            for k, v in t.items():
                if k != "name":
                    f.write(f"    {k}: {v}\n")
            f.write("\n")

        f.write(f"\nWEBSOCKET TOURNAMENTS FOUND: {len(ws_tournaments)}\n")
        for t in ws_tournaments:
            f.write(f"  {json.dumps(t, indent=4)}\n")

        f.write(f"\nREST API DATA FILES:\n")
        for fname in sorted(OUTPUT_DIR.glob("*.json")):
            f.write(f"  {fname.name}\n")

    log.info(f"Summary saved to {summary_path}")
    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--all"

    rest_data = {}
    ws_tournaments = []

    if mode in ("--all", "--rest-only"):
        scraper = RestScraper()
        rest_data = scraper.scrape_all()

    if mode in ("--all", "--ws-only"):
        ws = WebSocketScraper()
        ws_tournaments = await ws.scrape()

    if mode == "--discover":
        ws = WebSocketScraper()
        await ws.scrape(discover_mode=True)
        return

    generate_report(rest_data, ws_tournaments)

    log.info("=" * 60)
    log.info("SCRAPE COMPLETE")
    log.info(f"Output: {OUTPUT_DIR}")
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
