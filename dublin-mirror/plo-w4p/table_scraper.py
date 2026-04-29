#!/usr/bin/env python3
"""
PLO6 Table Scraper - Integrated with Bot Deployment
Scrapes available PLO6 tables from poker lobby and updates database.
"""

import os
import sys
import time
import json
import sqlite3
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

PLAYERS_DB = "/opt/plo-w4p/players.db"
SCRAPE_LOG = "/tmp/table_scraper.log"

# JavaScript to extract PLO6 tables from lobby
TABLE_SCRAPER_JS = """
(function() {
  const tables = [];

  // Target all table entries - adjust selectors based on actual lobby structure
  const selectors = [
    '[class*="table"]',
    '[class*="game"]',
    '[class*="lobby"]',
    '.lobby-item',
    '.game-item',
    '.table-item',
    'li[class*="item"]'
  ];

  const allElements = new Set();
  selectors.forEach(selector => {
    document.querySelectorAll(selector).forEach(el => allElements.add(el));
  });

  allElements.forEach(el => {
    const text = el.innerText || el.textContent || '';

    // Look for PLO6 or "Omaha 6" indicators
    if (text.match(/PLO6|Omaha.*6|6.*Card.*Omaha/i)) {
      // Extract table name (typically a city name)
      const nameMatch = text.match(/\\b([A-Z][a-z]+(?:\\s+[A-Z][a-z]+)*)\\b/);
      const name = nameMatch ? nameMatch[1] : null;

      // Extract stakes (ZAR X/Y format)
      const stakesMatch = text.match(/ZAR\\s+(\\d+(?:\\.\\d+)?)\\s*\\/\\s*(\\d+(?:\\.\\d+)?)/);

      // Extract seats (6-max, 9-max, etc.)
      const seatsMatch = text.match(/(\\d+)-max/i) || text.match(/(\\d+)\\s+seat/i);

      if (name && stakesMatch) {
        tables.push({
          name: name.trim(),
          game_type: 'PLO6',
          small_blind: parseFloat(stakesMatch[1]),
          big_blind: parseFloat(stakesMatch[2]),
          stakes_display: `ZAR ${stakesMatch[1]}/${stakesMatch[2]}`,
          seats_total: seatsMatch ? parseInt(seatsMatch[1]) : 6
        });
      }
    }
  });

  // Deduplicate by table name
  const uniqueTables = [];
  const seen = new Set();
  tables.forEach(t => {
    if (!seen.has(t.name)) {
      seen.add(t.name);
      uniqueTables.push(t);
    }
  });

  return uniqueTables;
})();
"""


def _log(msg):
    """Write to scraper log file."""
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with open(SCRAPE_LOG, "a") as f:
            f.write(line)
    except Exception:
        pass
    logger.info(msg)


def get_player_credentials():
    """Get first active player credentials for lobby access."""
    conn = sqlite3.connect(PLAYERS_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT username, password FROM players WHERE active=1 ORDER BY id LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {"username": row["username"], "password": row["password"]}


def navigate_to_lobby(driver, username, password):
    """Navigate to poker lobby using credentials."""
    _log("Navigating to pokerbet.co.za")
    driver.get("https://www.pokerbet.co.za")
    time.sleep(5)

    # Click SIGN IN button
    _log("Looking for SIGN IN button")
    sign_in_clicked = False
    for btn in driver.find_elements(By.TAG_NAME, "button"):
        if btn.text.strip() == "SIGN IN":
            driver.execute_script("arguments[0].click()", btn)
            _log("Clicked SIGN IN")
            sign_in_clicked = True
            break

    if not sign_in_clicked:
        raise Exception("SIGN IN button not found")

    time.sleep(3)

    # Fill login form
    _log(f"Filling login form for {username}")
    username_field = driver.find_element(By.CSS_SELECTOR, "input[name=username]")
    username_field.send_keys(username)

    password_field = driver.find_element(By.CSS_SELECTOR, "input[name=password]")
    password_field.send_keys(password)
    password_field.send_keys(Keys.RETURN)
    _log("Submitted login form")
    time.sleep(5)

    # Verify login
    body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
    if "balance" not in body_text and "deposit" not in body_text:
        raise Exception(f"Login failed for {username}")
    _log("Login successful")

    # Remove popups
    JS_REMOVE = 'document.querySelectorAll(".popup-middleware-bc,.popup-holder-bc").forEach(function(e){e.remove()})'
    driver.execute_script(JS_REMOVE)

    # Click POKER
    _log("Navigating to POKER section")
    for link in driver.find_elements(By.TAG_NAME, "a"):
        if link.text.strip() == "POKER":
            driver.execute_script("arguments[0].click()", link)
            break
    time.sleep(5)

    # Click PLAY
    _log("Clicking PLAY")
    for elem in driver.find_elements(By.TAG_NAME, "a") + driver.find_elements(By.TAG_NAME, "button"):
        if elem.text.strip() == "PLAY":
            driver.execute_script("arguments[0].click()", elem)
            break
    time.sleep(8)

    # Switch to poker iframe
    _log("Switching to poker iframe")
    iframe_found = False
    for iframe in driver.find_elements(By.TAG_NAME, "iframe"):
        src = iframe.get_attribute("src") or ""
        if "18751019" in src or "skillgames" in src:
            driver.switch_to.frame(iframe)
            _log("Switched to poker iframe")
            iframe_found = True
            break

    if not iframe_found:
        raise Exception("Poker iframe not found")

    time.sleep(3)

    # Click CASH GAMES
    _log("Navigating to CASH GAMES")
    for elem in driver.find_elements(By.XPATH, "//*[contains(text(),'CASH')]"):
        txt = elem.text.strip()
        if "CASH" in txt.upper() and len(txt) < 20:
            driver.execute_script("arguments[0].click()", elem)
            _log(f"Clicked: {txt}")
            break
    time.sleep(3)

    # Click LOBBY if visible
    for elem in driver.find_elements(By.XPATH, "//*[text()='LOBBY']"):
        driver.execute_script("arguments[0].click()", elem)
        _log("Clicked LOBBY")
        break
    time.sleep(3)

    # Scroll to load all tables
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)

    _log("Successfully navigated to lobby")


def scrape_tables(driver):
    """Execute JavaScript scraper and return table data."""
    _log("Executing table scraper JavaScript")
    try:
        tables = driver.execute_script(TABLE_SCRAPER_JS)
        _log(f"Scraper returned {len(tables)} tables")
        return tables
    except Exception as e:
        _log(f"JavaScript execution failed: {e}")
        return []


def update_database(tables):
    """Update poker_tables database with scraped data."""
    if not tables:
        _log("No tables to update in database")
        return {"updated": 0, "inserted": 0}

    conn = sqlite3.connect(PLAYERS_DB)
    cursor = conn.cursor()

    now = datetime.utcnow().isoformat()
    inserted = 0
    updated = 0

    for table in tables:
        # Check if table exists
        existing = cursor.execute(
            "SELECT id FROM poker_tables WHERE table_name = ?",
            (table["name"],)
        ).fetchone()

        if existing:
            # Update existing table
            cursor.execute("""
                UPDATE poker_tables
                SET game_type = ?,
                    seats_total = ?,
                    small_blind = ?,
                    big_blind = ?,
                    stakes_display = ?,
                    is_active = 1,
                    last_seen = ?
                WHERE table_name = ?
            """, (
                table["game_type"],
                table["seats_total"],
                table["small_blind"],
                table["big_blind"],
                table["stakes_display"],
                now,
                table["name"]
            ))
            updated += 1
        else:
            # Insert new table
            cursor.execute("""
                INSERT INTO poker_tables
                (table_name, game_type, seats_total, small_blind, big_blind, stakes_display, scraped_at, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                table["name"],
                table["game_type"],
                table["seats_total"],
                table["small_blind"],
                table["big_blind"],
                table["stakes_display"],
                now,
                now
            ))
            inserted += 1

    # Mark tables not seen in this scrape as inactive
    table_names = [t["name"] for t in tables]
    if table_names:
        placeholders = ",".join(["?"] * len(table_names))
        cursor.execute(f"""
            UPDATE poker_tables
            SET is_active = 0
            WHERE table_name NOT IN ({placeholders})
        """, table_names)

    conn.commit()
    conn.close()

    _log(f"Database updated: {inserted} inserted, {updated} updated")
    return {"inserted": inserted, "updated": updated}


def scrape_plo6_tables(headless=True):
    """
    Main entry point for table scraping.
    Returns: dict with status, tables list, and database stats.
    """
    start_time = time.time()
    _log("=== PLO6 Table Scraper Started ===")

    try:
        # Get credentials
        creds = get_player_credentials()
        if not creds:
            return {
                "ok": False,
                "error": "No active player credentials found",
                "tables": [],
                "duration": time.time() - start_time
            }

        # Setup Firefox
        os.environ["DISPLAY"] = ":1"
        options = Options()
        if headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        _log("Starting Firefox")
        driver = webdriver.Firefox(options=options)

        try:
            # Navigate to lobby
            navigate_to_lobby(driver, creds["username"], creds["password"])

            # Scrape tables
            tables = scrape_tables(driver)

            # Update database
            db_stats = update_database(tables)

            duration = time.time() - start_time
            _log(f"=== Scraping Complete ({duration:.1f}s) ===")

            return {
                "ok": True,
                "tables": tables,
                "count": len(tables),
                "database": db_stats,
                "duration": duration
            }

        finally:
            driver.quit()
            _log("Firefox closed")

    except Exception as e:
        import traceback
        error_msg = f"Scraper failed: {e}\n{traceback.format_exc()}"
        _log(error_msg)
        return {
            "ok": False,
            "error": str(e),
            "tables": [],
            "duration": time.time() - start_time
        }


if __name__ == "__main__":
    # Command-line usage
    headless = "--headless" in sys.argv
    result = scrape_plo6_tables(headless=headless)

    print(json.dumps(result, indent=2))

    if result["ok"]:
        print(f"\n✓ Found {result['count']} PLO6 tables")
        print(f"✓ Database: {result['database']['inserted']} new, {result['database']['updated']} updated")
        sys.exit(0)
    else:
        print(f"\n✗ Scraping failed: {result['error']}")
        sys.exit(1)
