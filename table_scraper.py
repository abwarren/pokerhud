#!/usr/bin/env python3
"""
PokerBet Tournament Table Scraper — Per-Table, Per-Hand, Per-Street
====================================================================
Scrapes active tournament tables, collects:
  - Player names, bet sizing (text size), per-street actions
  - Each hand: preflop → flop → turn → river actions for every player
  - Computes: VPIP, PFR, AF, 3-bet%, showdown hands

Separate-tier storage:
  - scraped_data/1k/           — ZAR 1K guaranteed tournaments
  - scraped_data/high_rollers/ — ZAR 5K+ (1K-5K, 5K, 10K, 20K+)
"""

import asyncio
import json
import time
import sys
import os
import re
import logging
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import requests
import websockets

# ── Config ──────────────────────────────────────────────────────────────────
PARTNER_ID = "18751019"
PRODUCT_ID = "3"
# Auth tokens — will refresh on each run
CLIENT_ID = "92311469"
CLIENT_ID_HASH = "8d96fa1aae7d4c613ab396f3677ee1e9a9bb4d75c233156a80774a462fa84a09"
PLAYER_ID = "357652843"
TOKEN = "2F90D07AC6E160842CFC8757484A5857"

WS_URL = "wss://poker-general.skillgames-bc.com"
GATEWAY_BASE = "https://sg-api.skillgames-bc.com"
CMS_BASE = "https://go-cms.pokerbet.co.za"

BASE_DIR = Path(__file__).parent / "scraped_data"
BASE_DIR.mkdir(exist_ok=True)

# Per-tier storage
TIER_1K = BASE_DIR / "1k"
TIER_HIGH = BASE_DIR / "high_rollers"
TIER_1K.mkdir(exist_ok=True)
TIER_HIGH.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TABLE] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "table_scraper.log"),
    ],
)
log = logging.getLogger("table_scraper")


# ── Board Texture Classifier ─────────────────────────────────────────────────
SUITS = {'h', 'd', 'c', 's'}
RANKS = {'2','3','4','5','6','7','8','9','T','J','Q','K','A'}

def classify_board_texture(board):
    """Classify flop board texture: monotone, paired, or rainbow."""
    if not board or len(board) < 3:
        return None
    flop = [c.strip() for c in board[:3]]
    suits = [c[-1] for c in flop if len(c) >= 2 and c[-1] in SUITS]
    ranks = [c[0] for c in flop if len(c) >= 2 and c[0] in RANKS]
    if len(suits) < 3 or len(ranks) < 3:
        return None
    suits_set = set(suits)
    ranks_set = set(ranks)
    if len(suits_set) == 1:
        return "monotone"
    if len(ranks_set) <= 2:
        return "paired"
    if len(suits_set) == 3:
        return "rainbow"
    return None


# ── Stats Engine ─────────────────────────────────────────────────────────────
class PlayerStats:
    MIN_HANDS_VPIP = 5
    MIN_HANDS_PFR = 5
    MIN_HANDS_3B = 10
    MIN_HANDS_AF = 5

    def __init__(self, name):
        self.name = name
        self.total_hands = 0
        self.vpip_count = 0
        self.pfr_count = 0
        self.three_bet_count = 0
        self.three_bet_opps = 0
        self.fold_count = 0
        self.call_count = 0
        self.raise_count = 0
        self.showdown_hands = 0
        self.showdown_wins = 0
        self.bet_sizings = []  # list of {street, pot_pct, spr, texture} per bet/raise

    def record_hand(self, actions, effective_stack=None, pot_at_start=None, board=None):
        """Record one hand's worth of actions for this player."""
        self.total_hands += 1
        has_voluntary = False
        has_pfr = False
        # Classify flop texture once per hand if board is available
        flop_texture = classify_board_texture(board) if board else None

        for act in actions:
            if act.get("type") == "fold":
                self.fold_count += 1
            elif act.get("type") == "call":
                self.call_count += 1
                if act.get("street") == "preflop" and not act.get("is_blind"):
                    has_voluntary = True
            elif act.get("type") in ("raise", "bet"):
                self.raise_count += 1
                if act.get("street") == "preflop" and not act.get("is_blind"):
                    has_voluntary = True
                    if act.get("is_raise"):
                        has_pfr = True
                    if act.get("is_three_bet"):
                        self.three_bet_count += 1
                        self.three_bet_opps += 1
                    elif act.get("is_three_bet_opp"):
                        self.three_bet_opps += 1

                # Track bet sizing — unit is % of pot
                if "amount" in act or "pot_pct" in act:
                    pot_pct = act.get("pot_pct")
                    # If we have raw amount + pot, calculate % of pot
                    if pot_pct is None and act.get("amount") and act.get("pot"):
                        pot_pct = round(act["amount"] / act["pot"] * 100, 1)
                    sizing = {
                        "street": act.get("street", "preflop"),
                        "pot_pct": pot_pct,
                        "amount": act.get("amount"),
                        "spr": None,
                        "texture": flop_texture if act.get("street") == "flop" else None,
                    }
                    # Compute SPR = effective stack / pot entering this street
                    esp = effective_stack or act.get("effective_stack")
                    pot_now = act.get("pot")
                    if esp and pot_now and pot_now > 0:
                        sizing["spr"] = round(esp / pot_now, 1)
                    self.bet_sizings.append(sizing)

            if act.get("showdown") and act.get("result") == "won":
                self.showdown_hands += 1
                self.showdown_wins += 1
            elif act.get("showdown"):
                self.showdown_hands += 1

        if has_voluntary:
            self.vpip_count += 1
        if has_pfr:
            self.pfr_count += 1

    def compute(self):
        """Compute final stats."""
        stats = {"player": self.name, "hands": self.total_hands}

        if self.total_hands >= self.MIN_HANDS_VPIP:
            stats["vpip"] = round(self.vpip_count / self.total_hands * 100, 1)
        else:
            stats["vpip"] = None

        if self.total_hands >= self.MIN_HANDS_PFR:
            stats["pfr"] = round(self.pfr_count / self.total_hands * 100, 1)
        else:
            stats["pfr"] = None

        if self.three_bet_opps >= self.MIN_HANDS_3B:
            stats["three_bet"] = round(
                self.three_bet_count / self.three_bet_opps * 100, 1
            )
        else:
            stats["three_bet"] = None

        af_denom = self.call_count + self.fold_count
        if af_denom > 0 and self.total_hands >= self.MIN_HANDS_AF:
            stats["af"] = round(self.raise_count / af_denom, 2)
        else:
            stats["af"] = None

        stats["showdown_hands"] = self.showdown_hands
        if self.showdown_hands > 0:
            stats["wtsd"] = round(self.showdown_hands / self.total_hands * 100, 1)
            stats["won_at_sd"] = round(
                self.showdown_wins / self.showdown_hands * 100, 1
            )
        else:
            stats["wtsd"] = None
            stats["won_at_sd"] = None

        # Bet sizing — measured as % of pot
        if self.bet_sizings:
            pot_pcts = [b["pot_pct"] for b in self.bet_sizings if b.get("pot_pct") is not None]
            if pot_pcts:
                stats["avg_bet_pot_pct"] = round(sum(pot_pcts) / len(pot_pcts), 1)
                stats["max_bet_pot_pct"] = max(pot_pcts)
                stats["min_bet_pot_pct"] = min(pot_pcts)
            # Per-street breakdown
            for street in ("preflop", "flop", "turn", "river"):
                street_sizings = [b["pot_pct"] for b in self.bet_sizings
                                  if b.get("street") == street and b.get("pot_pct") is not None]
                if street_sizings:
                    stats[f"avg_{street}_pot_pct"] = round(sum(street_sizings) / len(street_sizings), 1)
                    stats[f"count_{street}"] = len(street_sizings)
            # By board texture (flop only)
            for texture in ("monotone", "paired", "rainbow"):
                tex_sizings = [b["pot_pct"] for b in self.bet_sizings
                               if b.get("texture") == texture and b.get("pot_pct") is not None]
                if tex_sizings:
                    stats[f"avg_{texture}_pot_pct"] = round(sum(tex_sizings) / len(tex_sizings), 1)
                    stats[f"count_{texture}"] = len(tex_sizings)
            # SPR context
            sprs = [b["spr"] for b in self.bet_sizings if b.get("spr") is not None]
            if sprs:
                stats["avg_spr"] = round(sum(sprs) / len(sprs), 1)
                stats["min_spr"] = min(sprs)
        else:
            stats["avg_bet_pot_pct"] = None

        return stats


# ── Tournament Schedule Scraper ──────────────────────────────────────────────
def scrape_schedule():
    """Scrape tournament schedule from CMS + REST APIs."""
    tournaments = []
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/146.0",
        "Origin": "https://poker-web.pokerbet.co.za",
        "Referer": "https://poker-web.pokerbet.co.za/",
    }
    session.headers.update(headers)

    # CMS promotions (includes tournament schedules)
    try:
        url = f"{CMS_BASE}/api/public/v1/eng/partners/{PARTNER_ID}/promotions"
        r = session.get(
            url,
            params={"use_webp": "1", "platform": "0", "category": "poker", "country": "ZA"},
            timeout=15,
        )
        data = r.json()
        items = data.get("data", []) if isinstance(data, dict) else data
        if isinstance(items, dict):
            items = list(items.values())
            if items and isinstance(items[0], list):
                items = items[0]

        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")
            content = item.get("content", "")
            text = f"{title} {content}".lower()

            # Extract buy-in info
            buyin_match = re.search(r"r\s*(\d[\d,]*)\s*\+\s*r?\s*(\d*)", text, re.IGNORECASE)
            gtd_match = re.search(r"(?:guaranteed|gtd|guarantee).{0,20}r\s*(\d[\d,]*)", text, re.IGNORECASE)
            schedule_match = re.search(r"(every|daily|weekly|monday|tuesday|wednesday|thursday|friday|saturday|sunday).{0,30}\d{1,2}:\d{2}", text, re.IGNORECASE)

            t = {
                "title": title,
                "source": "cms",
                "buyin_raw": buyin_match.group(0) if buyin_match else None,
                "guarantee_raw": gtd_match.group(0) if gtd_match else None,
                "schedule": schedule_match.group(0) if schedule_match else None,
            }
            tournaments.append(t)

        log.info(f"Scraped {len(tournaments)} tournaments from CMS")
    except Exception as e:
        log.warning(f"CMS scrape failed: {e}")

    return tournaments


# ── Tier Classifier ──────────────────────────────────────────────────────────
# Minimum: only scrape tournaments with buy-in ≥ R10,000
MIN_BUYIN_10K = 10000

def classify_tournament(name, buyin_zar):
    """Classify a tournament into a data tier based on buy-in/guarantee.
    Only returns 'high' (10K+) or 'other' (skip)."""
    name_lower = name.lower() if name else ""

    # Check for known 10K+ tournaments by name
    # Matches: R125k, 250k, 10k, 20k, R1M, 1M, "1 000 000 GTD" etc.
    gtd_patterns = [
        (r"(?:r\s*)?(?:1[0-9]|[2-9]\d|1[0-4]\d)\s*k", "high"),  # 10k-149k (any "R" prefix)
        (r"(?:r\s*)?1[5-9]\d\s*k", "high"),                      # 150k-199k
        (r"(?:r\s*)?2\d{2}\s*k", "high"),                        # 200k-299k
        (r"(?:r\s*)?[3-9]\d{2}\s*k", "high"),                    # 300k-999k
        (r"(?:r\s*)?[1-9]\s*m(?:il)?", "high"),                  # 1M-9M
        (r"(?:r\s*)?(?:100|20[05-9]|2[1-9]\d|[3-9]\d{2}|1\d{3}),?\d{3}", "high"),  # R100,000+ literal numbers
    ]

    for pattern, tier in gtd_patterns:
        if re.search(pattern, name_lower, re.IGNORECASE):
            return tier

    # Fall back to buy-in amount — only 10K+
    if buyin_zar is not None and buyin_zar >= MIN_BUYIN_10K:
        return "high"

    return "other"  # below 10K — skip


# ── Hand Snapshot Parser ────────────────────────────────────────────────────
def parse_table_snapshot(raw_data):
    """
    Parse a raw table snapshot into structured per-player per-street hands.
    Expected input: dict with players[], board[], actions[], handId, etc.
    """
    hands = []
    players = raw_data.get("players", [])
    actions = raw_data.get("actions", [])
    board = raw_data.get("board", [])

    if not players:
        return hands

    # Group actions by player
    player_actions = defaultdict(list)
    for act in actions:
        player_actions[act.get("player", "")].append(act)

    # Build per-player hand record
    for p in players:
        name = p.get("name", "")
        if not name:
            continue
        p_acts = player_actions.get(name, [])

        hand = {
            "player": name,
            "position": p.get("position"),
            "stack": p.get("stack") or p.get("chips"),
            "cards": p.get("cards", []),
            "is_hero": p.get("isHero", False),
            "is_sitting_out": p.get("isSittingOut", False),
            "actions": [],
        }

        for act in p_acts:
            hand["actions"].append({
                "street": act.get("street", "preflop"),
                "type": act.get("type"),
                "amount": act.get("amount"),
                "pot": act.get("pot") or act.get("Pot"),
                "effective_stack": act.get("effectiveStack") or act.get("stackBefore", p.get("stack")),
                "is_raise": act.get("type") == "raise",
                "is_all_in": act.get("isAllIn", False),
                "pot_pct": act.get("potPct"),
                "timestamp": act.get("timestamp"),
            })

        hand["board"] = board
        hands.append(hand)

    return hands


# ── Per-Player Action Extractor (from live table DOM logging) ───────────────
def extract_actions_from_log(log_lines):
    """
    Parse structured log lines into player actions per street.
    Expected format:
      [ACTION] PlayerName: raise to 150 (preflop)
      [ACTION] PlayerName: call 50 (flop)
      [SHOWDOWN] PlayerName: shows AhKh
    """
    hands = []
    current_hand = {"hand_id": None, "players": {}, "board": [], "actions": []}

    for line in log_lines:
        line = line.strip()
        if not line:
            continue

        # New hand marker
        hm = re.search(r"\[HAND\s*(\d+|\w+)\]", line)
        if hm:
            if current_hand["actions"]:
                hands.append(current_hand)
            current_hand = {"hand_id": hm.group(1), "players": {}, "board": [], "actions": []}
            continue

        # Action line
        am = re.search(r"\[ACTION\]\s+(\S[\w\s.-]+?):\s+(fold|check|call|raise|bet|all.in)\s*([\d,.]*)\s*\((\w+)\)", line, re.IGNORECASE)
        if am:
            current_hand["actions"].append({
                "player": am.group(1).strip(),
                "type": am.group(2).lower(),
                "amount": float(am.group(3).replace(",", "")) if am.group(3) else 0,
                "street": am.group(4).lower(),
            })
            continue

        # Board cards
        bm = re.search(r"\[BOARD\]\s*([\s\w\d,]+)", line)
        if bm:
            cards = re.findall(r"[2-9TJQKA][shdc]", bm.group(1))
            current_hand["board"] = cards
            continue

        # Showdown
        sm = re.search(r"\[SHOWDOWN\]\s+(\S[\w\s.-]+?):\s+shows\s+([\w\s]+)", line, re.IGNORECASE)
        if sm:
            for act in current_hand["actions"]:
                if act["player"] == sm.group(1).strip():
                    act["showdown"] = True
                    act["show_cards"] = sm.group(2)
            continue

    if current_hand["actions"]:
        hands.append(current_hand)

    return hands


# ── Data Storage ────────────────────────────────────────────────────────────
def store_hand_data(tournament_name, buyin_zar, hands_data, stats):
    """Store parsed hand data + computed stats only for 10K+ tournaments."""
    tier = classify_tournament(tournament_name, buyin_zar)
    if tier != "high":
        log.info(f"Skipping sub-10K tournament: {tournament_name} (buy-in {buyin_zar})")
        return None, None

    out_dir = TIER_HIGH

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^a-zA-Z0-9]", "_", tournament_name)[:30]

    # Store raw hands
    hands_file = out_dir / f"hands_{safe_name}_{timestamp}.json"
    with open(hands_file, "w") as f:
        json.dump(
            {
                "tournament": tournament_name,
                "buyin_zar": buyin_zar,
                "scraped_at": datetime.now().isoformat(),
                "total_hands": len(hands_data),
                "hands": hands_data,
            },
            f,
            indent=2,
            default=str,
        )

    # Store computed stats
    stats_file = out_dir / f"stats_{safe_name}_{timestamp}.json"
    with open(stats_file, "w") as f:
        json.dump(
            {
                "tournament": tournament_name,
                "buyin_zar": buyin_zar,
                "computed_at": datetime.now().isoformat(),
                "players": len(stats),
                "stats": stats,
            },
            f,
            indent=2,
            default=str,
        )

    log.info(f"Stored {len(hands_data)} hands, {len(stats)} players → {out_dir}")
    return hands_file, stats_file


# ── Summary Reporter ─────────────────────────────────────────────────────────
def generate_summary(stats_by_tier):
    """Generate a summary of all collected stats by tier."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"POKERBET TABLE SCRAPE SUMMARY")
    lines.append(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)

    for tier_name, tier_data in stats_by_tier.items():
        lines.append(f"\n── {tier_name.upper()} ──")
        lines.append(f"  Tournaments: {len(tier_data.get('tournaments', []))}")
        lines.append(f"  Total hands: {tier_data.get('total_hands', 0)}")
        lines.append(f"  Players tracked: {len(tier_data.get('players', {}))}")
        lines.append(f"\n  Player Stats:")

        stats_list = tier_data.get("stats", [])
        stats_list.sort(key=lambda s: s.get("hands", 0), reverse=True)

        for s in stats_list[:20]:
            vpip = f"{s.get('vpip', '?')}%" if s.get("vpip") else "?"
            pfr = f"{s.get('pfr', '?')}%" if s.get("pfr") else "?"
            threeb = f"{s.get('three_bet', '?')}%" if s.get("three_bet") else "?"
            af = f"{s.get('af', '?')}" if s.get("af") else "?"
            sd = f"{s.get('showdown_hands', 0)}"
            wtsd = f"{s.get('wtsd', '?')}%" if s.get("wtsd") else "?"
            bet_pf = f"P{s.get('avg_preflop_pot_pct', '?'):>4}" if s.get("avg_preflop_pot_pct") else "P   ?"
            bet_f = f"F{s.get('avg_flop_pot_pct', '?'):>4}" if s.get("avg_flop_pot_pct") else "F   ?"
            bet_t = f"T{s.get('avg_turn_pot_pct', '?'):>4}" if s.get("avg_turn_pot_pct") else "T   ?"
            bet_r = f"R{s.get('avg_river_pot_pct', '?'):>4}" if s.get("avg_river_pot_pct") else "R   ?"
            # Texture (if available)
            tex_parts = []
            for t in ("monotone", "paired", "rainbow"):
                v = s.get(f"avg_{t}_pot_pct")
                if v:
                    tex_parts.append(f"{t[:3]}={v:g}%P")
            tex_str = "  [" + " ".join(tex_parts) + "]" if tex_parts else ""
            spr_str = f" @SPR{s.get('avg_spr', '?')}" if s.get("avg_spr") else ""
            lines.append(
                f"  {s['player']:16s} H={s['hands']:3d}  "
                f"VP={vpip:>5}  PF={pfr:>5}  3B={threeb:>5}  "
                f"AF={af:>4}  SD={sd:>2}  WTS={wtsd:>5}"
            )
            lines.append(
                f"  {'':16s} Bet  {bet_pf} {bet_f} {bet_t} {bet_r}{spr_str}{tex_str}"
            )

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


# ── Main Scraper ────────────────────────────────────────────────────────────
def run_scrape():
    """Main entry point — scrape schedule and collect table data."""
    log.info("=" * 60)
    log.info("POKERBET TOURNAMENT TABLE SCRAPER")
    log.info("=" * 60)

    # Step 1: Get schedule
    tournaments = scrape_schedule()
    log.info(f"Schedule: {len(tournaments)} tournaments found")

    # Step 2: For each active tournament, try to scrape table data
    # Only tracking 10K+ tournaments
    all_stats_by_tier = {
        "high_rollers": {"tournaments": [], "total_hands": 0, "players": {}, "stats": []},
    }

    # Compute player stats from any available hand data
    player_stats = {}

    # Try WebSocket connection for live table data (30-second scrape)
    async def ws_scrape():
        nonlocal player_stats
        try:
            extra_headers = {
                "Origin": "https://poker-web.pokerbet.co.za",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/146.0",
            }
            async with websockets.connect(
                WS_URL, additional_headers=extra_headers,
                ping_interval=30, ping_timeout=10, close_timeout=5,
            ) as ws:
                log.info("WebSocket connected")

                # Send auth + lobby subscription
                cmds = [
                    {"cmd": "login", "partnerId": int(PARTNER_ID),
                     "clientId": int(CLIENT_ID), "token": TOKEN,
                     "playerId": int(PLAYER_ID)},
                    {"cmd": "getLobby", "productId": int(PRODUCT_ID)},
                    {"cmd": "getTournaments", "partnerId": int(PARTNER_ID)},
                    {"cmd": "subscribe", "channel": "tournaments",
                     "partnerId": int(PARTNER_ID)},
                ]

                for cmd in cmds:
                    await ws.send(json.dumps(cmd))
                    await asyncio.sleep(0.3)

                # Listen for responses
                responses = []
                for _ in range(30):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        try:
                            parsed = json.loads(msg)
                            responses.append(parsed)
                        except json.JSONDecodeError:
                            pass
                    except asyncio.TimeoutError:
                        continue

                log.info(f"Received {len(responses)} WS messages")
                if responses:
                    ws_file = BASE_DIR / f"ws_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(ws_file, "w") as f:
                        json.dump(responses, f, indent=2, default=str)

                    for resp in responses:
                        if isinstance(resp, dict):
                            t_list = resp.get("tournaments") or resp.get("data", {}).get("tournaments")
                            if t_list:
                                for t in t_list:
                                    if isinstance(t, dict):
                                        name = t.get("name", t.get("Name", "?"))
                                        buyin = t.get("buyIn", t.get("BuyIn")) or t.get("buy_in")
                                        if buyin:
                                            try:
                                                buyin_zar = float(buyin)
                                            except (ValueError, TypeError):
                                                buyin_zar = None
                                        else:
                                            buyin_zar = None
                                        tier = classify_tournament(name, buyin_zar)
                                        tier_key = {"1k": "1k", "high": "high_rollers", "other": "other"}[tier]
                                        all_stats_by_tier[tier_key]["tournaments"].append({
                                            "name": name,
                                            "buyin": buyin_zar,
                                            "players_registered": t.get("playersRegistered", t.get("players", 0)),
                                            "max_players": t.get("playersMax", t.get("maxPlayers")),
                                            "status": t.get("status"),
                                            "start_time": t.get("startTime", t.get("StartTime")),
                                        })

        except Exception as e:
            log.warning(f"WebSocket scrape failed: {e}")

    asyncio.run(ws_scrape())

    # Step 3: Compute and store stats per tier
    for tier_key, tier_data in all_stats_by_tier.items():
        if tier_data["tournaments"]:
            summary_path = BASE_DIR / tier_key / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(summary_path, "w") as f:
                json.dump(tier_data, f, indent=2, default=str)
            log.info(f"{tier_key}: {len(tier_data['tournaments'])} tournaments tracked")

    # Step 4: Generate final summary
    summary = generate_summary(all_stats_by_tier)
    summary_path = BASE_DIR / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(summary_path, "w") as f:
        f.write(summary)
    log.info(f"\n{summary}")
    log.info(f"Summary saved to {summary_path}")

    return all_stats_by_tier


if __name__ == "__main__":
    run_scrape()
