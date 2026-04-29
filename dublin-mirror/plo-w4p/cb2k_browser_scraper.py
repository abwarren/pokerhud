#!/usr/bin/env python3
"""
CB2K Browser Scraper — pulls Cyber Basketball 2K26 results from PokerBet
Uses Selenium headless Chrome to render JS and extract game data.
Navigates to results pages and scrapes historical completed games.
"""
import json
import time
import sys
import os
import re
import sqlite3
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BLM_DB = '/opt/plo-w4p/blm.db'
RESULTS_URL = 'https://www.pokerbet.co.za/en/sports/pre-match/results'
SPORT_URL = 'https://www.pokerbet.co.za/en/sports/pre-match/sport/Basketball/18295203'

def get_driver():
    """Create headless Chrome driver."""
    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--disable-extensions')
    opts.add_argument('--disable-notifications')
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

    # Try different chromedriver locations
    for path in ['/usr/bin/chromedriver', '/usr/local/bin/chromedriver', 'chromedriver']:
        if os.path.exists(path):
            service = Service(executable_path=path)
            return webdriver.Chrome(service=service, options=opts)

    # Fallback — let Selenium find it
    return webdriver.Chrome(options=opts)


def extract_swarm_data(driver):
    """
    Inject JS to intercept BetConstruct swarm WebSocket data.
    The PokerBet frontend communicates via WebSocket — we can capture the data.
    """
    # Inject network interceptor
    script = """
    return new Promise((resolve) => {
        // Check if angular/betconstruct data is available in window
        var data = {};

        // BetConstruct stores data in various global objects
        if (window.Swarm) data.swarm = 'found';
        if (window.BettingData) data.betting = JSON.stringify(window.BettingData).substring(0, 2000);
        if (window.__INITIAL_STATE__) data.initial = JSON.stringify(window.__INITIAL_STATE__).substring(0, 2000);

        // Check Angular scope
        var appEl = document.querySelector('[ng-app], [data-ng-app], .app-bc');
        if (appEl && window.angular) {
            var scope = window.angular.element(appEl).scope();
            if (scope) data.scope = Object.keys(scope).filter(k => !k.startsWith('$')).join(', ');
        }

        // Check for results data in the DOM
        var results = [];
        var rows = document.querySelectorAll('[class*="result-row"], [class*="game-result"], tr[class*="bc"]');
        rows.forEach(function(row) {
            var text = row.textContent.trim();
            if (text.length > 5) results.push(text.substring(0, 200));
        });
        data.resultRows = results.length;
        data.sampleRows = results.slice(0, 5);

        // Get all visible text content related to basketball/cyber
        var allText = document.body.innerText || '';
        var lines = allText.split('\\n').filter(l =>
            l.toLowerCase().includes('cyber') ||
            l.toLowerCase().includes('basketball') ||
            l.toLowerCase().includes('2k26') ||
            /\\d+\\s*[-:]\\s*\\d+/.test(l)
        );
        data.matchingLines = lines.slice(0, 30);

        // Get all links on page
        var links = [];
        document.querySelectorAll('a[href*="game"], a[href*="result"], a[href*="basket"]').forEach(function(a) {
            links.push({href: a.href, text: a.textContent.trim().substring(0, 100)});
        });
        data.links = links.slice(0, 20);

        resolve(JSON.stringify(data));
    });
    """
    try:
        result = driver.execute_script(script)
        return json.loads(result) if result else {}
    except Exception as e:
        return {'error': str(e)}


def scrape_results_page(driver, game_id=None):
    """Navigate to results page and extract game data."""
    url = RESULTS_URL
    if game_id:
        url += f'?game={game_id}'

    print(f"[NAV] {url}")
    driver.get(url)
    time.sleep(5)  # Wait for Angular to render

    # Extract page data
    data = extract_swarm_data(driver)
    print(f"[DATA] {json.dumps(data, indent=2)[:1000]}")

    return data


def scrape_sport_page(driver):
    """Navigate to Basketball sport page to find competitions."""
    print(f"\n[NAV] Sport page: {SPORT_URL}")
    driver.get(SPORT_URL)
    time.sleep(5)

    data = extract_swarm_data(driver)
    print(f"[SPORT] {json.dumps(data, indent=2)[:1000]}")

    # Also try to find competition/league links
    script = """
    var comps = [];
    document.querySelectorAll('[class*="competition"], [class*="league"], [class*="tournament"]').forEach(function(el) {
        comps.push({
            tag: el.tagName,
            cls: el.className.substring(0, 100),
            text: el.textContent.trim().substring(0, 200),
            children: el.children.length
        });
    });

    // Also get sidebar navigation
    var nav = [];
    document.querySelectorAll('[class*="sp-sub-list"], [class*="sport-item"], [class*="sidebar"]').forEach(function(el) {
        nav.push({
            cls: el.className.substring(0, 80),
            text: el.textContent.trim().substring(0, 200)
        });
    });

    return JSON.stringify({competitions: comps.slice(0, 20), navigation: nav.slice(0, 20)});
    """
    try:
        result = driver.execute_script(script)
        extra = json.loads(result) if result else {}
        print(f"[COMPS] {json.dumps(extra, indent=2)[:1000]}")
        return {**data, **extra}
    except Exception as e:
        print(f"[ERROR] {e}")
        return data


def find_cyber_basketball_games(driver):
    """
    Navigate through PokerBet to find and list all Cyber Basketball 2K26 games.
    """
    print("\n" + "="*60)
    print("Phase 1: Finding Cyber Basketball 2K26 competitions")
    print("="*60)

    # Try the basketball sport page
    sport_data = scrape_sport_page(driver)

    # Try navigating to specific cyber basketball
    cyber_urls = [
        'https://www.pokerbet.co.za/en/sports/pre-match/sport/Basketball/18295203/cyber-basketball-2k26-matches',
        'https://www.pokerbet.co.za/en/sports/pre-match/sport/Basketball/18295203',
        'https://www.pokerbet.co.za/en/sports/live/sport/Basketball',
    ]

    for url in cyber_urls:
        print(f"\n[TRY] {url}")
        driver.get(url)
        time.sleep(4)

        # Look for game links
        script = """
        var games = [];
        // Look for event-view links (individual games)
        document.querySelectorAll('a[href*="event-view"]').forEach(function(a) {
            var href = a.href;
            var match = href.match(/(\\d{7,})/g);
            if (match) {
                games.push({
                    href: href,
                    ids: match,
                    text: a.textContent.trim().substring(0, 150)
                });
            }
        });

        // Also look for game rows
        document.querySelectorAll('[class*="hm-row"], [class*="game-row"], [class*="event-row"]').forEach(function(el) {
            var links = el.querySelectorAll('a[href]');
            links.forEach(function(a) {
                if (a.href.includes('event-view') || a.href.includes('game')) {
                    games.push({
                        href: a.href,
                        text: el.textContent.trim().substring(0, 200)
                    });
                }
            });
        });

        // Check page title and content for cyber basketball
        var bodyText = document.body.innerText;
        var hasCyber = bodyText.toLowerCase().includes('cyber');
        var has2k26 = bodyText.toLowerCase().includes('2k26');

        return JSON.stringify({
            games: games.slice(0, 50),
            hasCyber: hasCyber,
            has2k26: has2k26,
            title: document.title,
            bodyLength: bodyText.length
        });
        """
        try:
            result = driver.execute_script(script)
            page_data = json.loads(result) if result else {}
            print(f"  Games found: {len(page_data.get('games', []))}")
            print(f"  Has Cyber: {page_data.get('hasCyber')}, Has 2K26: {page_data.get('has2k26')}")
            if page_data.get('games'):
                for g in page_data['games'][:5]:
                    print(f"    {g.get('text', '')[:80]} -> {g.get('href', '')[-60:]}")
                return page_data
        except Exception as e:
            print(f"  Error: {e}")

    return None


def scrape_game_result(driver, game_url):
    """Scrape a single game's results page."""
    driver.get(game_url)
    time.sleep(3)

    script = """
    var result = {teams: [], scores: [], quarters: [], markets: []};

    // Team names
    document.querySelectorAll('[class*="team-name"]').forEach(function(el) {
        result.teams.push(el.textContent.trim());
    });

    // Main score
    document.querySelectorAll('[class*="score-item"], [class*="total-score"]').forEach(function(el) {
        var n = parseFloat(el.textContent.trim());
        if (!isNaN(n)) result.scores.push(n);
    });

    // Quarter scores (set scores)
    document.querySelectorAll('[class*="set-score"]').forEach(function(el) {
        result.quarters.push(el.textContent.trim());
    });

    // Market data (Total line)
    document.querySelectorAll('[class*="market-name"]').forEach(function(el) {
        var text = el.textContent.trim();
        if (text.toLowerCase().includes('total') || text.toLowerCase().includes('over') || text.toLowerCase().includes('under')) {
            result.markets.push(text);
        }
    });

    // Game ID from URL
    var match = location.pathname.match(/(\\d{7,})/);
    result.gameId = match ? match[match.length - 1] : null;

    // All visible text
    result.allText = document.body.innerText.substring(0, 3000);

    return JSON.stringify(result);
    """
    try:
        result = driver.execute_script(script)
        return json.loads(result) if result else {}
    except Exception as e:
        return {'error': str(e)}


def main():
    print("=" * 60)
    print("CB2K Browser Scraper")
    print("Selenium + Chrome headless")
    print("=" * 60)

    driver = get_driver()
    print(f"[OK] Chrome launched")

    try:
        # Phase 1: Find games
        games_data = find_cyber_basketball_games(driver)

        # Phase 2: Try results page with known game ID
        print("\n" + "="*60)
        print("Phase 2: Scraping known game results")
        print("="*60)

        known_ids = ['29585435', '28744451']
        for gid in known_ids:
            print(f"\n[GAME] {gid}")
            result = scrape_results_page(driver, game_id=gid)

        # Phase 3: Try to find the main results listing
        print("\n" + "="*60)
        print("Phase 3: Results listing page")
        print("="*60)

        driver.get(RESULTS_URL)
        time.sleep(5)

        script = """
        var page = {sections: [], games: []};

        // All text content
        var text = document.body.innerText;
        var lines = text.split('\\n').filter(l => l.trim().length > 3);
        page.lines = lines.slice(0, 100);
        page.totalLines = lines.length;

        // Find score patterns (e.g., "109 - 96", "Cleveland 205")
        lines.forEach(function(line) {
            if (/\\d+\\s*[-:]\\s*\\d+/.test(line) || /cyber/i.test(line)) {
                page.games.push(line.trim().substring(0, 200));
            }
        });

        // DOM structure
        var els = document.querySelectorAll('[class*="-bc"]');
        var classes = {};
        els.forEach(function(el) {
            var cls = el.className.split(' ')[0];
            classes[cls] = (classes[cls] || 0) + 1;
        });
        page.bcClasses = classes;

        return JSON.stringify(page);
        """
        result = driver.execute_script(script)
        page_data = json.loads(result) if result else {}

        print(f"\n[RESULTS PAGE]")
        print(f"  Total lines: {page_data.get('totalLines', 0)}")
        print(f"  Game-like lines: {len(page_data.get('games', []))}")

        if page_data.get('games'):
            print("\n  Score lines:")
            for line in page_data['games'][:20]:
                print(f"    {line}")

        if page_data.get('lines'):
            print("\n  First 30 page lines:")
            for line in page_data['lines'][:30]:
                print(f"    {line}")

        if page_data.get('bcClasses'):
            print("\n  BC classes:")
            for cls, count in sorted(page_data['bcClasses'].items(), key=lambda x: -x[1])[:20]:
                print(f"    {cls}: {count}")

    except Exception as e:
        print(f"\n[FATAL] {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()
        print("\n[DONE] Chrome closed")


if __name__ == '__main__':
    main()
