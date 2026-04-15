#!/usr/bin/env python3
"""
Tournament Scraper → Supabase
Scrapes PokerBet CMS promotions and Sunbet poker data → pushes to Supabase.

For LIVE lobby tournament data (buy-ins, guarantees, schedules), the Chrome
extension content script scrapes the BetConstruct skillgames lobby directly
and sends it via POST /api/snapshot. This scraper handles the CMS/marketing
data that doesn't require authentication.

Run: python3 tournament_scraper_live.py
"""

import json
import re
import os
import sys
from datetime import datetime, timezone
from html import unescape
from urllib.parse import quote

import requests

# ============================================
# SUPABASE CONFIG
# ============================================
SUPABASE_URL = "https://kzqrdtagpykoylhuqcyv.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt6cXJkdGFncHlrb3lsaHVxY3l2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwNzMxMDQsImV4cCI6MjA5MTY0OTEwNH0.wfmyJ8sf1QZK4w3BWfYd-_JdIKUfgPkUl9Fz4Nnv-OI"

HEADERS_SUPABASE = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}

# ============================================
# POKERBET CONFIG (Partner ID: 18751019)
# ============================================
# Use only go-cms — cmsbetconstruct.com returns identical data
POKERBET_CMS = "https://go-cms.pokerbet.co.za/api/public/v1/eng/partners/18751019"

# Poker-specific keywords for filtering CMS promotions
# These must appear in the TITLE (not body, which always mentions "Pokerbet")
POKER_TITLE_KEYWORDS = [
    "tournament", "slam", "satellite", "freeroll",
    "buy-in", "buy in", "guarantee", "omaha",
    "holdem", "hold'em", "hold em", "nlhe", "plo",
    "rake back", "rakeback", "cash game", "sit & go",
    "sit and go", "bounty", "freezeout", "rebuy",
    "add-on", "addon", "turbo", "hyper", "deep stack",
    "poker", "nightly", "weekly", "daily",
]

# Items whose TITLE matches these are definitely NOT poker tournaments
NON_POKER_INDICATORS = [
    "sport welcome", "casino welcome", "casino boost",
    "cricket", "rugby", "pit stop", "sport booster",
    "acca boost", "sponsorship", "formula", "motorsport",
    "soccer", "football", "basketball", "tennis",
    "slots", "roulette", "blackjack", "baccarat",
    "sponsorship",
]


def strip_html(html_text):
    """Remove HTML tags and decode entities."""
    if not html_text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', html_text)
    text = unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def parse_zar_amount(text):
    """Extract ZAR amount from text like 'R200,000' or 'R700+R70'."""
    if not text:
        return None
    match = re.search(r'R\s?([\d,]+(?:\.\d+)?)', text.replace(' ', ''))
    if match:
        return float(match.group(1).replace(',', ''))
    return None


# ============================================
# POKERBET CMS SCRAPER
# ============================================
def scrape_pokerbet_promotions():
    """Scrape poker promotions from PokerBet CMS (single endpoint, deduplicated)."""
    tournaments = []
    seen_ids = set()

    try:
        url = f"{POKERBET_CMS}/promotions"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # CMS wraps items in {code, text, success, data: [...]}
        items = []
        if isinstance(data, dict) and "data" in data:
            raw = data["data"]
            if isinstance(raw, list):
                items = raw
            elif isinstance(raw, dict):
                for v in raw.values():
                    if isinstance(v, list):
                        items.extend(v)
        elif isinstance(data, list):
            items = data

        for item in items:
            if not isinstance(item, dict):
                continue

            # Deduplicate by CMS item ID
            item_id = str(item.get("id", ""))
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            title = item.get("title", "")
            content = strip_html(item.get("content", ""))
            title_lower = title.lower()

            # Two-stage filter:
            # 1. Reject if title matches known non-poker patterns
            if any(ind in title_lower for ind in NON_POKER_INDICATORS):
                print(f"    SKIP (non-poker): {title[:60]}")
                continue

            # 2. Accept only if title contains poker-game keywords
            #    (body always mentions "Pokerbet" so we filter on title only)
            if not any(kw in title_lower for kw in POKER_TITLE_KEYWORDS):
                print(f"    SKIP (no poker keywords in title): {title[:60]}")
                continue

            full_text = f"{title} {content}".lower()

            t = {
                "site": "pokerbet",
                "source": "cms",
                "external_id": item_id,
                "name": title,
                "description": content[:500],
                "image_url": item.get("src", ""),
                "raw_data": item,
                "scraped_at": datetime.now(timezone.utc).isoformat()
            }

            # Parse buy-in (R700+R70 format)
            buyin_match = re.search(r'R\s?(\d+)\s*\+\s*R\s?(\d+)', content)
            if buyin_match:
                t["buy_in_entry_zar"] = float(buyin_match.group(1))
                t["buy_in_fee_zar"] = float(buyin_match.group(2))
                t["buy_in_total_zar"] = t["buy_in_entry_zar"] + t["buy_in_fee_zar"]

            # Parse guarantee
            gtd_match = re.search(r'(?:guarantee|guaranteed)[^R]*R\s?([\d,]+)', full_text, re.I)
            if gtd_match:
                guarantee = parse_zar_amount(gtd_match.group(0))
                if guarantee:
                    t["prize_pool_guaranteed_zar"] = guarantee

            # Parse schedule day
            for day in ["sunday", "saturday", "monday", "tuesday", "wednesday", "thursday", "friday"]:
                if day in full_text:
                    t["schedule_day"] = day
                    break

            # Parse start time
            time_match = re.search(r'(\d{1,2})[:\.](\d{2})\s*(am|pm)', full_text)
            if time_match:
                t["start_time"] = f"{time_match.group(1)}:{time_match.group(2)} {time_match.group(3)}"

            # Detect satellite
            if "satellite" in full_text:
                t["is_satellite"] = True
                sat_buyin = re.search(r'(?:as little as|from)\s*R\s?(\d+)', full_text, re.I)
                if sat_buyin:
                    t["satellite_min_buy_in_zar"] = float(sat_buyin.group(1))

            # Detect game type
            if "omaha" in full_text or "plo" in full_text:
                t["game_type"] = "PLO"
            elif "hold" in full_text or "nlhe" in full_text:
                t["game_type"] = "NLHE"

            # Detect rakeback
            rb_match = re.search(r'(\d+)%\s*(?:of\s*)?(?:your\s*)?(?:total\s*)?rake', full_text)
            if rb_match:
                t["rakeback_pct"] = float(rb_match.group(1))
                min_match = re.search(r'min.*?payout.*?R\s?([\d,]+)', full_text, re.I)
                max_match = re.search(r'max.*?(?:payout)?.*?R\s?([\d,]+)', full_text, re.I)
                if min_match:
                    t["min_payout_zar"] = float(min_match.group(1).replace(',', ''))
                if max_match:
                    t["max_payout_zar"] = float(max_match.group(1).replace(',', ''))

            tournaments.append(t)

        print(f"  [PokerBet CMS] {len(items)} total items, {len(tournaments)} poker-related")

    except Exception as e:
        print(f"  [PokerBet CMS] Error: {e}")

    return tournaments


def scrape_pokerbet_banners():
    """Scrape poker banners from PokerBet CMS."""
    tournaments = []

    try:
        url = f"{POKERBET_CMS}/components/poker_banners/contents"
        params = {"use_webp": "1", "platform": "0", "country": "ZA"}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Extract items from response
        items = []
        if isinstance(data, dict) and "data" in data:
            raw = data["data"]
            items = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
        elif isinstance(data, list):
            items = data

        seen_names = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")
            if not title or title in seen_names:
                continue
            seen_names.add(title)

            t = {
                "site": "pokerbet",
                "source": "banner",
                "name": title,
                "image_url": item.get("src", item.get("image", "")),
                "link_url": item.get("link", item.get("url", "")),
                "description": strip_html(item.get("content", item.get("description", "")))[:500],
                "raw_data": item,
                "scraped_at": datetime.now(timezone.utc).isoformat()
            }
            tournaments.append(t)

        print(f"  [PokerBet Banners] {len(tournaments)} banners found")

    except Exception as e:
        print(f"  [PokerBet Banners] Error: {e}")

    return tournaments


# ============================================
# SUNBET SCRAPER
# ============================================
def scrape_sunbet():
    """
    Scrape poker tournament info from Sunbet.

    Note: Sunbet uses Bede Gaming (not BetConstruct). Their poker tournament
    data is login-gated with no public API. We can only scrape publicly
    visible promotional content from the marketing pages.
    """
    tournaments = []
    seen_names = set()

    urls = [
        "https://www.sunbet.co.za",
        "https://www.sunbet.co.za/poker",
    ]

    for url in urls:
        try:
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0"
            })
            html = resp.text

            # Find poker-related images (exclude casino/slots tournament banners)
            banner_pattern = re.findall(
                r'(?:src|href)="([^"]*(?:poker|holdem|omaha)[^"]*)"',
                html, re.I
            )

            for banner_url in set(banner_pattern):
                if not any(ext in banner_url.lower() for ext in ['.webp', '.png', '.jpg']):
                    continue
                name = re.sub(r'[-_]', ' ', banner_url.split('/')[-1].split('.')[0]).title()
                if name in seen_names or len(name) < 3:
                    continue
                seen_names.add(name)

                t = {
                    "site": "sunbet",
                    "source": "banner",
                    "name": name,
                    "image_url": banner_url if banner_url.startswith('http') else f"https://www.sunbet.co.za{banner_url}",
                    "scraped_at": datetime.now(timezone.utc).isoformat()
                }
                tournaments.append(t)

            # Look for structured JSON data in page scripts
            script_data = re.findall(r'(?:promotions|tournaments)\s*[:=]\s*(\[.*?\])', html, re.S)
            for sd in script_data:
                try:
                    items = json.loads(sd)
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        name = item.get("title", item.get("name", ""))
                        if not name or name in seen_names:
                            continue
                        # Only poker-related items
                        item_text = f"{name} {item.get('content', '')} {item.get('description', '')}".lower()
                        if not any(kw in item_text for kw in POKER_KEYWORDS):
                            continue
                        seen_names.add(name)
                        t = {
                            "site": "sunbet",
                            "source": "script_data",
                            "name": name,
                            "description": strip_html(item.get("content", item.get("description", "")))[:500],
                            "raw_data": item,
                            "scraped_at": datetime.now(timezone.utc).isoformat()
                        }
                        tournaments.append(t)
                except json.JSONDecodeError:
                    pass

            print(f"  [Sunbet] {url}: {len(tournaments)} poker items found")

        except Exception as e:
            print(f"  [Sunbet] Error scraping {url}: {e}")

    return tournaments


# ============================================
# SUPABASE PUSH (with deduplication)
# ============================================
def push_to_supabase(tournaments):
    """Upsert tournaments to Supabase with deduplication."""
    if not tournaments:
        print("  No tournaments to push")
        return 0

    url = f"{SUPABASE_URL}/rest/v1/tournaments"
    success = 0
    seen = set()

    for t in tournaments:
        # Clean None values
        clean = {k: v for k, v in t.items() if v is not None}

        # Ensure required fields
        if not clean.get("name"):
            continue
        clean.setdefault("site", "unknown")
        clean.setdefault("source", "scraper")

        # Deduplicate by (site, name, source)
        dedup_key = (clean["site"], clean["name"], clean["source"])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Convert raw_data to JSON string
        if "raw_data" in clean and not isinstance(clean["raw_data"], str):
            clean["raw_data"] = json.dumps(clean["raw_data"])

        try:
            resp = requests.post(
                url,
                headers=HEADERS_SUPABASE,
                json=clean,
                timeout=10
            )

            if resp.status_code in (200, 201):
                success += 1
            elif resp.status_code == 409:
                # Conflict — update existing row
                filter_url = (
                    f"{url}?site=eq.{quote(clean['site'])}"
                    f"&name=eq.{quote(clean['name'])}"
                    f"&source=eq.{quote(clean['source'])}"
                )
                resp2 = requests.patch(
                    filter_url,
                    headers=HEADERS_SUPABASE,
                    json=clean,
                    timeout=10
                )
                if resp2.status_code in (200, 204):
                    success += 1
                else:
                    print(f"  Update failed for {clean['name']}: {resp2.status_code} {resp2.text[:200]}")
            else:
                print(f"  Push failed for {clean['name']}: {resp.status_code} {resp.text[:200]}")

        except Exception as e:
            print(f"  Error pushing {clean.get('name')}: {e}")

    return success


def delete_junk_from_supabase():
    """Delete non-poker CMS entries and duplicates from Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/tournaments"
    deleted = 0

    # Known non-poker CMS items to delete
    junk_names = [
        "Sport Welcome Bonus Ts&Cs",
        "Casino Welcome Bonus + 50 Free Spins Ts&Cs",
        "Casino Boost Wednesday Ts&Cs",
        "The Ultimate Cricket Tour- Ts&Cs",
        "Rugby Score Predictor Ts&Cs",
        "Pit Stop Protection - Ts&Cs",
        "Sport Booster Ts&Cs",
        "Acca Boost Terms and Conditions",
    ]

    for name in junk_names:
        try:
            filter_url = f"{url}?name=eq.{quote(name)}&source=eq.cms"
            resp = requests.delete(filter_url, headers=HEADERS_SUPABASE, timeout=10)
            if resp.status_code in (200, 204):
                deleted += 1
                print(f"    Deleted: {name}")
            else:
                print(f"    Delete failed for {name}: {resp.status_code}")
        except Exception as e:
            print(f"    Error deleting {name}: {e}")

    # Delete non-poker Sunbet banners (casino slot tournaments)
    sunbet_junk = [
        "Endorphina Tournament April Desktop",
        "Endorphina Tournament April Mobile",
    ]
    for name in sunbet_junk:
        try:
            filter_url = f"{url}?name=eq.{quote(name)}&site=eq.sunbet"
            resp = requests.delete(filter_url, headers=HEADERS_SUPABASE, timeout=10)
            if resp.status_code in (200, 204):
                deleted += 1
                print(f"    Deleted: {name}")
        except Exception as e:
            print(f"    Error deleting {name}: {e}")

    return deleted


# ============================================
# MAIN
# ============================================
def main():
    print("=" * 60)
    print("TOURNAMENT SCRAPER → SUPABASE")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 0: Clean junk from previous scrapes
    print("\n[0] Cleaning junk from Supabase...")
    cleaned = delete_junk_from_supabase()
    print(f"  Cleaned {cleaned} junk entries")

    all_tournaments = []

    # Step 1: PokerBet CMS promotions (poker-filtered, deduplicated)
    print("\n[1] Scraping PokerBet CMS promotions...")
    pb_promos = scrape_pokerbet_promotions()
    all_tournaments.extend(pb_promos)

    # Step 2: PokerBet banners
    print("\n[2] Scraping PokerBet banners...")
    pb_banners = scrape_pokerbet_banners()
    all_tournaments.extend(pb_banners)

    # Step 3: Sunbet (limited — poker data is login-gated)
    print("\n[3] Scraping Sunbet public pages...")
    sb = scrape_sunbet()
    all_tournaments.extend(sb)

    # Summary
    print(f"\n{'='*60}")
    print(f"TOTAL SCRAPED: {len(all_tournaments)}")
    if all_tournaments:
        for site in sorted(set(t["site"] for t in all_tournaments)):
            count = sum(1 for t in all_tournaments if t["site"] == site)
            print(f"  {site}: {count}")
        print()
        for t in all_tournaments:
            buyin = t.get("buy_in_total_zar", "")
            gtd = t.get("prize_pool_guaranteed_zar", "")
            print(f"  [{t['site']}/{t['source']}] {t['name'][:55]:55s} buyin={buyin} gtd={gtd}")
    else:
        print("  (no items scraped)")

    # Push to Supabase
    print(f"\n[4] Pushing to Supabase...")
    pushed = push_to_supabase(all_tournaments)
    print(f"  Successfully pushed: {pushed}/{len(all_tournaments)}")

    # Verify final DB state
    print(f"\n[5] Verifying Supabase state...")
    verify_supabase()

    # Save local copy
    out_path = "/opt/pokerhud/tournament_data/latest_scrape.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(all_tournaments, f, indent=2, default=str)
    print(f"\n  Saved to {out_path}")

    print(f"\n{'='*60}")
    print("DONE")


def verify_supabase():
    """Print summary of what's in the tournaments table."""
    url = f"{SUPABASE_URL}/rest/v1/tournaments?select=name,site,source&order=site,name"
    try:
        resp = requests.get(url, headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
        }, timeout=10)
        data = resp.json()
        print(f"  Total in DB: {len(data)}")
        from collections import Counter
        sources = Counter(f"{t['site']}/{t['source']}" for t in data)
        for src, count in sorted(sources.items()):
            print(f"    {src}: {count}")
    except Exception as e:
        print(f"  Verify error: {e}")


if __name__ == "__main__":
    main()
