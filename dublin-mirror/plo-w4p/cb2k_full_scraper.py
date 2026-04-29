#!/usr/bin/env python3
"""
CB2K Full Scraper — Pull ALL Cyber Basketball 2K26 results from PokerBet
Navigates the results filter, selects Basketball > Cyber Basketball 2K26,
iterates through date ranges, and saves all games to BLM database.
"""
import json
import time
import sys
import os
import re
import sqlite3
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

BLM_DB = '/opt/plo-w4p/blm.db'
RESULTS_URL = 'https://www.pokerbet.co.za/en/sports/pre-match/results'

def get_driver():
    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    for path in ['/usr/bin/chromedriver', '/usr/local/bin/chromedriver']:
        if os.path.exists(path):
            return webdriver.Chrome(service=Service(executable_path=path), options=opts)
    return webdriver.Chrome(options=opts)


def init_db():
    db = sqlite3.connect(BLM_DB)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT UNIQUE NOT NULL,
            league TEXT DEFAULT 'Cyber Basketball 2K26',
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            home_score INTEGER,
            away_score INTEGER,
            total_score INTEGER,
            q1_home INTEGER, q1_away INTEGER,
            q2_home INTEGER, q2_away INTEGER,
            q3_home INTEGER, q3_away INTEGER,
            q4_home INTEGER, q4_away INTEGER,
            ot_home INTEGER, ot_away INTEGER,
            status TEXT DEFAULT 'final',
            game_date TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date);
    """)
    db.commit()
    return db


def save_game(db, game):
    """Save a game to the database."""
    try:
        db.execute("""
            INSERT OR REPLACE INTO games
            (game_id, league, home_team, away_team,
             home_score, away_score, total_score,
             q1_home, q1_away, q2_home, q2_away,
             q3_home, q3_away, q4_home, q4_away,
             status, game_date, updated_at)
            VALUES (?, 'Cyber Basketball 2K26', ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    'final', ?, datetime('now'))
        """, (
            game['game_id'], game['home_team'], game['away_team'],
            game['home_score'], game['away_score'], game['total_score'],
            game.get('q1_home'), game.get('q1_away'),
            game.get('q2_home'), game.get('q2_away'),
            game.get('q3_home'), game.get('q3_away'),
            game.get('q4_home'), game.get('q4_away'),
            game.get('game_date')
        ))
        return True
    except Exception as e:
        print(f"  [DB ERROR] {e}")
        return False


def parse_score_line(text):
    """
    Parse score like: '101:113 (23:22, 18:37, 24:23, 36:31)'
    Returns dict with scores and quarter breakdowns.
    """
    result = {}
    # Main score: "101:113"
    main = re.match(r'(\d+)\s*:\s*(\d+)', text)
    if not main:
        return None
    result['home_score'] = int(main.group(1))
    result['away_score'] = int(main.group(2))
    result['total_score'] = result['home_score'] + result['away_score']

    # Quarter scores in parentheses
    quarters = re.findall(r'(\d+):(\d+)', text)
    if len(quarters) >= 2:  # First match is the total, rest are quarters
        for i, (h, a) in enumerate(quarters[1:], 1):
            if i <= 4:
                result[f'q{i}_home'] = int(h)
                result[f'q{i}_away'] = int(a)

    return result


def scrape_all_results(driver, db):
    """
    Navigate to results page, select Basketball + Cyber Basketball 2K26,
    and scrape all available games.
    """
    print(f"[NAV] {RESULTS_URL}")
    driver.get(RESULTS_URL)
    time.sleep(5)

    total_saved = 0

    # Strategy: Use JS to interact with the filters and extract data
    # The results page has: Sport dropdown, Competition dropdown, date range, SHOW button

    # First, let's see what competitions are available for Basketball
    setup_script = """
    // Click on Sport dropdown and select Basketball
    var sportDropdowns = document.querySelectorAll('select, [class*="dropdown"], [class*="select"]');
    var result = {dropdowns: [], options: []};

    sportDropdowns.forEach(function(dd, i) {
        result.dropdowns.push({
            index: i,
            tag: dd.tagName,
            cls: dd.className.substring(0, 100),
            text: dd.textContent.trim().substring(0, 200),
            type: dd.type || ''
        });
    });

    // Check for custom dropdown (BetConstruct uses custom dropdowns)
    var customDDs = document.querySelectorAll('[class*="filter"], [class*="results-filter"]');
    customDDs.forEach(function(dd) {
        result.options.push({
            cls: dd.className.substring(0, 100),
            text: dd.textContent.trim().substring(0, 300),
            children: dd.children.length
        });
    });

    // Get all visible text to understand page structure
    result.pageText = document.body.innerText.substring(0, 3000);

    return JSON.stringify(result);
    """
    setup_data = json.loads(driver.execute_script(setup_script))
    print(f"[SETUP] Dropdowns: {len(setup_data.get('dropdowns', []))}")
    print(f"[SETUP] Filter elements: {len(setup_data.get('options', []))}")

    # Now try to select Basketball and find Cyber Basketball
    select_script = """
    return new Promise(async (resolve) => {
        var results = {steps: [], games: []};

        // Step 1: Find and click the Sport selector to pick Basketball
        var allElements = document.body.innerText;
        results.steps.push('Page loaded, looking for filters...');

        // BetConstruct uses custom dropdowns. Let's find them.
        var filterArea = document.querySelector('[class*="results-filter"], [class*="filter-area"]');
        if (!filterArea) {
            // Try finding by the structure we saw: "Sport" label followed by dropdown
            var labels = document.querySelectorAll('label, [class*="label"]');
            labels.forEach(l => {
                if (l.textContent.trim() === 'Sport') {
                    filterArea = l.parentElement;
                    results.steps.push('Found Sport label');
                }
            });
        }

        // Find all clickable filter items
        var filterItems = document.querySelectorAll('[class*="filter-item"], [class*="dropdown-item"], [class*="option"]');
        results.steps.push('Filter items: ' + filterItems.length);

        // Look for "Basketball" in any dropdown/select element
        var selects = document.querySelectorAll('select');
        for (var i = 0; i < selects.length; i++) {
            var sel = selects[i];
            var opts = sel.options;
            for (var j = 0; j < opts.length; j++) {
                if (opts[j].text.toLowerCase().includes('basket')) {
                    results.steps.push('Found Basketball option in select #' + i + ': ' + opts[j].text);
                    sel.value = opts[j].value;
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                    results.steps.push('Selected Basketball, waiting...');
                    break;
                }
            }
        }

        // Wait for competitions to load
        await new Promise(r => setTimeout(r, 2000));

        // Now look for Cyber Basketball 2K26 in competition selector
        selects = document.querySelectorAll('select');
        for (var i = 0; i < selects.length; i++) {
            var sel = selects[i];
            var opts = sel.options;
            var optTexts = [];
            for (var j = 0; j < opts.length; j++) {
                optTexts.push(opts[j].text);
                if (opts[j].text.toLowerCase().includes('cyber') || opts[j].text.toLowerCase().includes('2k26')) {
                    results.steps.push('Found Cyber option: ' + opts[j].text + ' (value: ' + opts[j].value + ')');
                    sel.value = opts[j].value;
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                    results.steps.push('Selected Cyber Basketball');
                }
            }
            if (optTexts.length > 1) {
                results.steps.push('Select #' + i + ' options: ' + optTexts.slice(0, 15).join(', '));
            }
        }

        // Wait again
        await new Promise(r => setTimeout(r, 1000));

        // Click SHOW button
        var showBtn = null;
        document.querySelectorAll('button, [class*="button"]').forEach(function(btn) {
            if (btn.textContent.trim().toUpperCase() === 'SHOW') {
                showBtn = btn;
            }
        });
        if (showBtn) {
            showBtn.click();
            results.steps.push('Clicked SHOW');
            await new Promise(r => setTimeout(r, 3000));
        } else {
            results.steps.push('SHOW button not found');
        }

        // Now scrape all results
        var blocks = document.querySelectorAll('[class*="results-block-bc"]');
        results.steps.push('Result blocks found: ' + blocks.length);

        // Extract from the text matching lines
        var bodyText = document.body.innerText;
        var lines = bodyText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

        // Parse game blocks
        // Pattern: Team1 \\n Team2 \\n Score (quarters) \\n Date
        var i = 0;
        while (i < lines.length - 2) {
            var line = lines[i];
            // Check if this looks like a team name (contains "Cyber")
            if (line.toLowerCase().includes('cyber') && i + 2 < lines.length) {
                var home = line;
                var away = lines[i + 1];
                var scoreLine = lines[i + 2];

                // Verify score pattern
                var scoreMatch = scoreLine.match(/(\\d+)\\s*:\\s*(\\d+)\\s*\\((.+)\\)/);
                if (scoreMatch) {
                    var game = {
                        home_team: home,
                        away_team: away,
                        score_line: scoreLine,
                        home_score: parseInt(scoreMatch[1]),
                        away_score: parseInt(scoreMatch[2]),
                        total: parseInt(scoreMatch[1]) + parseInt(scoreMatch[2]),
                        quarters_raw: scoreMatch[3]
                    };

                    // Parse quarters
                    var qMatches = scoreMatch[3].match(/(\\d+):(\\d+)/g) || [];
                    qMatches.forEach(function(q, qi) {
                        var parts = q.split(':');
                        game['q' + (qi+1) + '_home'] = parseInt(parts[0]);
                        game['q' + (qi+1) + '_away'] = parseInt(parts[1]);
                    });

                    // Try to get game ID from nearby links
                    results.games.push(game);
                    i += 3;
                    continue;
                }
            }
            i++;
        }

        results.steps.push('Games parsed: ' + results.games.length);
        resolve(JSON.stringify(results));
    });
    """

    try:
        result = json.loads(driver.execute_script(select_script))
    except Exception as e:
        print(f"[ERROR] {e}")
        result = {}

    steps = result.get('steps', [])
    games = result.get('games', [])

    print(f"\n[FILTER STEPS]:")
    for s in steps:
        print(f"  {s}")

    print(f"\n[GAMES FOUND] {len(games)}")

    # Save games to database
    for i, game in enumerate(games):
        # Generate game_id from teams + score (since we may not have the BC game ID)
        gid = f"cb2k_{game['home_team'][:10]}_{game['away_team'][:10]}_{game['home_score']}_{game['away_score']}".replace(' ', '_').lower()
        game['game_id'] = gid

        if save_game(db, game):
            total_saved += 1
            print(f"  [{i+1}] {game['home_team']} {game['home_score']} - {game['away_score']} {game['away_team']} (Total: {game['total']})")

    db.commit()

    # If we didn't find games through filters, try pagination / scrolling
    if len(games) == 0:
        print("\n[FALLBACK] Trying to scroll and load more results...")
        scroll_script = """
        return new Promise(async (resolve) => {
            // Scroll to load more results
            var scrollable = document.querySelector('[class*="results-content"], [class*="scrollable"], .main-area');
            if (!scrollable) scrollable = document.documentElement;

            for (var i = 0; i < 5; i++) {
                scrollable.scrollTop += 500;
                await new Promise(r => setTimeout(r, 1000));
            }

            // Re-extract all text
            var text = document.body.innerText;
            resolve(text.substring(0, 10000));
        });
        """
        page_text = driver.execute_script(scroll_script)
        print(f"\n[PAGE TEXT (first 3000 chars)]:")
        print(page_text[:3000] if page_text else "Empty")

    return total_saved


def scrape_by_game_ids(driver, db):
    """
    Brute-force approach: iterate through game IDs near known ones
    and scrape each result page.
    """
    print("\n" + "="*60)
    print("Phase 2: Scraping by game ID range")
    print("="*60)

    # Known game IDs from user
    base_ids = [29585435, 28744451]
    # Games run every ~5 minutes, ~288/day, ~8640/month
    # Scan a range around known IDs

    # Start from the lower known ID and scan forward
    start_id = 28744451
    end_id = 29600000
    step = 10  # Try every 10th ID first to find the pattern

    total_saved = 0
    misses = 0
    max_misses = 20  # Stop after 20 consecutive misses

    # First pass: sample to find valid ranges
    print(f"[SCAN] Range {start_id} to {end_id}, step {step}")
    valid_ranges = []
    test_ids = list(range(start_id, end_id, 5000))  # Sample every 5000

    for test_id in test_ids[:10]:  # Quick sample
        driver.get(f"{RESULTS_URL}?game={test_id}")
        time.sleep(2)

        script = """
        var lines = document.body.innerText.split('\\n').filter(l =>
            l.toLowerCase().includes('cyber') ||
            /\\d+:\\d+\\s*\\(/.test(l)
        );
        return JSON.stringify(lines.slice(0, 5));
        """
        result = json.loads(driver.execute_script(script) or '[]')
        if result and any('cyber' in str(r).lower() for r in result):
            valid_ranges.append(test_id)
            print(f"  [HIT] {test_id}: {result[0][:80] if result else ''}")
        else:
            print(f"  [MISS] {test_id}")

    if not valid_ranges:
        print("[INFO] No valid ranges found in sample. Using known game IDs only.")
        valid_ranges = base_ids

    # Now scan around valid ranges more densely
    print(f"\n[DETAIL SCAN] Around {len(valid_ranges)} valid points")

    all_games = []
    seen_scores = set()

    for center in valid_ranges:
        scan_ids = list(range(max(center - 100, start_id), min(center + 100, end_id), 2))
        for gid in scan_ids:
            driver.get(f"{RESULTS_URL}?game={gid}")
            time.sleep(1.5)

            script = """
            var result = null;
            var lines = document.body.innerText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

            for (var i = 0; i < lines.length - 2; i++) {
                if (lines[i].toLowerCase().includes('cyber')) {
                    var home = lines[i];
                    var away = lines[i+1];
                    var scoreMatch = (lines[i+2] || '').match(/(\\d+)\\s*:\\s*(\\d+)\\s*\\((.+)\\)/);
                    if (scoreMatch) {
                        result = {
                            game_id: String(""" + str(gid) + """),
                            home_team: home,
                            away_team: away,
                            home_score: parseInt(scoreMatch[1]),
                            away_score: parseInt(scoreMatch[2]),
                            total: parseInt(scoreMatch[1]) + parseInt(scoreMatch[2]),
                            quarters_raw: scoreMatch[3]
                        };
                        var qMatches = scoreMatch[3].match(/(\\d+):(\\d+)/g) || [];
                        qMatches.forEach(function(q, qi) {
                            var parts = q.split(':');
                            result['q' + (qi+1) + '_home'] = parseInt(parts[0]);
                            result['q' + (qi+1) + '_away'] = parseInt(parts[1]);
                        });
                        break;
                    }
                }
            }
            return result ? JSON.stringify(result) : null;
            """
            raw = driver.execute_script(script)
            if raw:
                game = json.loads(raw)
                # Dedup by teams+score
                key = f"{game['home_team']}_{game['away_team']}_{game['home_score']}_{game['away_score']}"
                if key not in seen_scores:
                    seen_scores.add(key)
                    game['game_id'] = str(gid)
                    if save_game(db, game):
                        total_saved += 1
                        print(f"  [{total_saved}] #{gid}: {game['home_team']} {game['home_score']}-{game['away_score']} {game['away_team']} = {game['total']}")
                    misses = 0
                else:
                    misses = 0  # Still valid, just a dupe
            else:
                misses += 1
                if misses >= max_misses:
                    print(f"  [SKIP] {max_misses} consecutive misses, moving to next range")
                    misses = 0
                    break

    db.commit()
    return total_saved


def main():
    print("=" * 60)
    print("CB2K Full Scraper — All Cyber Basketball 2K26 Results")
    print("=" * 60)

    db = init_db()
    driver = get_driver()
    print("[OK] Chrome + DB ready")

    try:
        # Phase 1: Try filter-based scraping
        saved1 = scrape_all_results(driver, db)
        print(f"\n[PHASE 1] Saved {saved1} games via filters")

        # Phase 2: Game ID range scan
        saved2 = scrape_by_game_ids(driver, db)
        print(f"\n[PHASE 2] Saved {saved2} games via ID scan")

        # Summary
        total = db.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        print(f"\n{'='*60}")
        print(f"TOTAL GAMES IN DATABASE: {total}")

        # Show some stats
        stats = db.execute("""
            SELECT COUNT(*) as n,
                   AVG(total_score) as avg_total,
                   MIN(total_score) as min_total,
                   MAX(total_score) as max_total,
                   AVG(home_score) as avg_home,
                   AVG(away_score) as avg_away
            FROM games WHERE total_score > 0
        """).fetchone()
        if stats:
            print(f"  Avg Total: {stats[1]:.1f}")
            print(f"  Min Total: {stats[2]}")
            print(f"  Max Total: {stats[3]}")
            print(f"  Avg Home: {stats[4]:.1f}")
            print(f"  Avg Away: {stats[5]:.1f}")

    except Exception as e:
        print(f"\n[FATAL] {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()
        db.close()
        print("\n[DONE]")


if __name__ == '__main__':
    main()
