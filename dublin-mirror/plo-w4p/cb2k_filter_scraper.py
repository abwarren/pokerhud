#!/usr/bin/env python3
"""
CB2K Filter Scraper - Uses PokerBet results page filters to pull
all Cyber Basketball 2K26 results. Selects Sport=Basketball,
Competition=Cyber Basketball 2K26, date range, then clicks SHOW.
"""
import json, time, re, sqlite3, os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

DB = '/tmp/blm.db'
URL = 'https://www.pokerbet.co.za/en/sports/pre-match/results'

opts = Options()
opts.add_argument('--headless'); opts.add_argument('--no-sandbox')
opts.add_argument('--disable-dev-shm-usage'); opts.add_argument('--disable-gpu')
opts.add_argument('--window-size=1920,1080')
opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

driver = None
for p in ['/usr/bin/chromedriver', '/usr/local/bin/chromedriver']:
    if os.path.exists(p):
        driver = webdriver.Chrome(service=Service(executable_path=p), options=opts)
        break
if not driver:
    driver = webdriver.Chrome(options=opts)
print("[OK] Chrome ready")

db = sqlite3.connect(DB)
db.execute("PRAGMA journal_mode=WAL")
db.executescript("""
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT UNIQUE NOT NULL,
    league TEXT DEFAULT 'Cyber Basketball 2K26',
    home_team TEXT NOT NULL, away_team TEXT NOT NULL,
    home_score INTEGER, away_score INTEGER, total_score INTEGER,
    q1_home INTEGER, q1_away INTEGER, q2_home INTEGER, q2_away INTEGER,
    q3_home INTEGER, q3_away INTEGER, q4_home INTEGER, q4_away INTEGER,
    ot_home INTEGER, ot_away INTEGER,
    status TEXT DEFAULT 'final', game_date TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
""")
db.commit()

try:
    # Step 1: Navigate to results page
    print(f"[NAV] {URL}")
    driver.get(URL)
    time.sleep(6)

    # Step 2: Explore the filter UI
    explore = driver.execute_script("""
    var r = {selects: [], buttons: [], inputs: [], page_text: ''};

    // Find all select elements
    document.querySelectorAll('select').forEach(function(sel, i) {
        var opts = [];
        for (var j = 0; j < sel.options.length; j++) {
            opts.push({value: sel.options[j].value, text: sel.options[j].text});
        }
        r.selects.push({index: i, id: sel.id, name: sel.name, cls: sel.className.substring(0,100), optCount: opts.length, options: opts.slice(0, 30)});
    });

    // Find buttons
    document.querySelectorAll('button, [class*="button"]').forEach(function(btn) {
        r.buttons.push({text: btn.textContent.trim().substring(0, 50), cls: btn.className.substring(0, 80), tag: btn.tagName});
    });

    // Find date inputs
    document.querySelectorAll('input[type="date"], input[type="text"][class*="date"], [class*="date-picker"], [class*="datepicker"]').forEach(function(inp) {
        r.inputs.push({type: inp.type, cls: inp.className.substring(0,80), id: inp.id, value: inp.value, placeholder: inp.placeholder});
    });

    r.page_text = document.body.innerText.substring(0, 2000);
    return JSON.stringify(r);
    """)
    data = json.loads(explore)

    print(f"\n[SELECTS] Found {len(data['selects'])}")
    for sel in data['selects']:
        print(f"  Select #{sel['index']}: {sel['optCount']} options, cls={sel['cls'][:50]}")
        for opt in sel['options'][:10]:
            print(f"    '{opt['text']}' = {opt['value']}")

    print(f"\n[BUTTONS] Found {len(data['buttons'])}")
    for btn in data['buttons'][:10]:
        print(f"  [{btn['tag']}] '{btn['text'][:40]}' cls={btn['cls'][:50]}")

    print(f"\n[INPUTS] Found {len(data['inputs'])}")
    for inp in data['inputs']:
        print(f"  type={inp['type']} id={inp['id']} val={inp['value']}")

    # Step 3: Select Basketball sport and find Cyber Basketball competition
    result = driver.execute_script("""
    return new Promise(async (resolve) => {
        var log = [];
        var selects = document.querySelectorAll('select');
        log.push('Found ' + selects.length + ' selects');

        // Find sport select (first select, or one containing "Football", "Basketball")
        var sportSel = null;
        var compSel = null;

        for (var i = 0; i < selects.length; i++) {
            var hasBasketball = false;
            var hasFootball = false;
            for (var j = 0; j < selects[i].options.length; j++) {
                var t = selects[i].options[j].text.toLowerCase();
                if (t.includes('basketball')) hasBasketball = true;
                if (t.includes('football')) hasFootball = true;
            }
            if (hasBasketball || hasFootball) {
                sportSel = selects[i];
                log.push('Sport select found at index ' + i + ' with ' + selects[i].options.length + ' options');
                break;
            }
        }

        if (!sportSel) {
            log.push('No sport select found. Selects: ' + selects.length);
            resolve(JSON.stringify({log: log, games: []}));
            return;
        }

        // Select Basketball
        for (var j = 0; j < sportSel.options.length; j++) {
            if (sportSel.options[j].text.toLowerCase().includes('basketball')) {
                sportSel.value = sportSel.options[j].value;
                sportSel.dispatchEvent(new Event('change', {bubbles: true}));
                log.push('Selected Basketball: value=' + sportSel.options[j].value);
                break;
            }
        }

        // Wait for competition dropdown to populate
        await new Promise(r => setTimeout(r, 3000));

        // Find competition select (should now have Cyber Basketball)
        selects = document.querySelectorAll('select');
        for (var i = 0; i < selects.length; i++) {
            if (selects[i] === sportSel) continue;
            var opts = [];
            for (var j = 0; j < selects[i].options.length; j++) {
                opts.push(selects[i].options[j].text);
            }
            log.push('Select #' + i + ': ' + opts.slice(0, 20).join(', '));

            // Find Cyber Basketball 2K26
            for (var j = 0; j < selects[i].options.length; j++) {
                var t = selects[i].options[j].text.toLowerCase();
                if (t.includes('cyber') || t.includes('2k26')) {
                    compSel = selects[i];
                    compSel.value = selects[i].options[j].value;
                    compSel.dispatchEvent(new Event('change', {bubbles: true}));
                    log.push('Selected: ' + selects[i].options[j].text + ' value=' + selects[i].options[j].value);
                    break;
                }
            }
        }

        if (!compSel) {
            log.push('No Cyber Basketball competition found');
        }

        // Wait
        await new Promise(r => setTimeout(r, 1000));

        // Click SHOW
        var showBtn = null;
        document.querySelectorAll('button').forEach(function(btn) {
            if (btn.textContent.trim().toUpperCase() === 'SHOW') showBtn = btn;
        });
        // Also try span/div with SHOW text
        if (!showBtn) {
            document.querySelectorAll('[class*="show"], [class*="submit"], [class*="search"]').forEach(function(el) {
                if (el.textContent.trim().toUpperCase() === 'SHOW') showBtn = el;
            });
        }

        if (showBtn) {
            showBtn.click();
            log.push('Clicked SHOW');
        } else {
            log.push('SHOW button not found, trying to click any submit');
            document.querySelectorAll('button[type="submit"], [class*="btn"]').forEach(function(btn) {
                var t = btn.textContent.trim().toLowerCase();
                if (t === 'show' || t === 'search' || t === 'submit' || t === 'apply') {
                    btn.click();
                    log.push('Clicked: ' + t);
                }
            });
        }

        // Wait for results
        await new Promise(r => setTimeout(r, 5000));

        // Parse all results
        var games = [];
        var text = document.body.innerText;
        var lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

        log.push('Total text lines: ' + lines.length);

        // Find game blocks: Team1 / Team2 / Score(quarters)
        for (var i = 0; i < lines.length - 2; i++) {
            var line = lines[i];
            if (line.toLowerCase().includes('cyber') && !line.includes('pokerbet') && !line.includes('2021')) {
                var home = line;
                var away = lines[i + 1];
                if (!away || away.length < 3 || away.includes('pokerbet')) continue;
                // Check for Cyber in away team too
                if (!away.toLowerCase().includes('cyber')) {
                    // Maybe the score is on the next line
                    var scoreCheck = lines[i + 1];
                    var sm = scoreCheck.match(/(\\d+)\\s*:\\s*(\\d+)\\s*\\((.+)\\)/);
                    if (sm) {
                        // This is: TeamCyber / Score — need to look back for the other team
                        continue;
                    }
                    continue;
                }

                // Look for score on next lines
                for (var k = i + 2; k < Math.min(i + 5, lines.length); k++) {
                    var scoreMatch = lines[k].match(/(\\d+)\\s*:\\s*(\\d+)\\s*\\((.+)\\)/);
                    if (scoreMatch) {
                        var g = {
                            home_team: home, away_team: away,
                            home_score: parseInt(scoreMatch[1]),
                            away_score: parseInt(scoreMatch[2]),
                            total: parseInt(scoreMatch[1]) + parseInt(scoreMatch[2]),
                            q_raw: scoreMatch[3]
                        };
                        var qs = scoreMatch[3].match(/(\\d+):(\\d+)/g) || [];
                        qs.forEach(function(q, qi) {
                            var p = q.split(':');
                            g['q' + (qi+1) + '_h'] = parseInt(p[0]);
                            g['q' + (qi+1) + '_a'] = parseInt(p[1]);
                        });
                        games.push(g);
                        i = k;
                        break;
                    }
                }
            }
        }

        log.push('Games parsed: ' + games.length);

        // Also get game IDs from links
        var links = [];
        document.querySelectorAll('a[href*="game="]').forEach(function(a) {
            var m = a.href.match(/game=(\\d+)/);
            if (m) links.push(m[1]);
        });
        log.push('Game ID links: ' + links.length);

        // Get competition blocks for context
        var blocks = document.querySelectorAll('[class*="results-block-bc"]');
        log.push('Result blocks: ' + blocks.length);

        // Extract from result blocks
        blocks.forEach(function(block) {
            var teamEls = block.querySelectorAll('[class*="results-teams-name-bc"]');
            var scoreEls = block.querySelectorAll('[class*="results-teams-score-bc"]');
            if (teamEls.length >= 2 && scoreEls.length >= 1) {
                var home = teamEls[0].textContent.trim();
                var away = teamEls[1].textContent.trim();
                var scoreText = scoreEls[0].textContent.trim();
                if ((home.toLowerCase().includes('cyber') || away.toLowerCase().includes('cyber')) && scoreText.includes(':')) {
                    var sm2 = scoreText.match(/(\\d+)\\s*:\\s*(\\d+)/);
                    if (sm2) {
                        var g2 = {
                            home_team: home, away_team: away,
                            home_score: parseInt(sm2[1]),
                            away_score: parseInt(sm2[2]),
                            total: parseInt(sm2[1]) + parseInt(sm2[2]),
                            source: 'dom_block'
                        };
                        // Check for quarter detail
                        var detailEls = block.querySelectorAll('[class*="results-game-details-events-bc"]');
                        var qText = '';
                        detailEls.forEach(function(d) { qText += d.textContent.trim() + ' '; });
                        var qs2 = qText.match(/(\\d+):(\\d+)/g) || [];
                        qs2.forEach(function(q, qi) {
                            var p = q.split(':');
                            g2['q' + (qi+1) + '_h'] = parseInt(p[0]);
                            g2['q' + (qi+1) + '_a'] = parseInt(p[1]);
                        });
                        games.push(g2);
                    }
                }
            }
        });

        log.push('Total games after DOM scan: ' + games.length);
        resolve(JSON.stringify({log: log, games: games, links: links}));
    });
    """)

    data = json.loads(result)

    print("\n[LOG]")
    for l in data.get('log', []):
        print(f"  {l}")

    games = data.get('games', [])
    links = data.get('links', [])
    print(f"\n[RESULTS] {len(games)} games, {len(links)} game ID links")

    saved = 0
    for g in games:
        gid = f"cb2k_{g['home_team'][:8]}_{g['away_team'][:8]}_{g['home_score']}_{g['away_score']}".replace(' ', '').lower()
        try:
            db.execute("""INSERT OR IGNORE INTO games
                (game_id, home_team, away_team, home_score, away_score, total_score,
                 q1_home, q1_away, q2_home, q2_away, q3_home, q3_away, q4_home, q4_away,
                 status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'final')""",
                (gid, g['home_team'], g['away_team'],
                 g['home_score'], g['away_score'], g['total'],
                 g.get('q1_h'), g.get('q1_a'), g.get('q2_h'), g.get('q2_a'),
                 g.get('q3_h'), g.get('q3_a'), g.get('q4_h'), g.get('q4_a')))
            saved += 1
        except Exception as e:
            pass
    db.commit()
    print(f"[SAVED] {saved} games from filter results")

    # Now if we have game ID links, scrape those individually
    if links:
        print(f"\n[INDIVIDUAL] Scraping {len(links)} game IDs...")
        for gid_str in links[:200]:
            try:
                driver.get(f"https://www.pokerbet.co.za/en/sports/pre-match/results?game={gid_str}")
                time.sleep(1.5)
                raw = driver.execute_script("""
                var lines = document.body.innerText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                for (var i = 0; i < lines.length - 2; i++) {
                    if (lines[i].toLowerCase().includes('cyber')) {
                        var away = lines[i+1];
                        if (!away || away.length < 3) continue;
                        for (var k = i+2; k < Math.min(i+5, lines.length); k++) {
                            var m = lines[k].match(/(\\d+)\\s*:\\s*(\\d+)\\s*\\((.+)\\)/);
                            if (m) {
                                var g = {home: lines[i], away: away,
                                    hs: parseInt(m[1]), as: parseInt(m[2]),
                                    t: parseInt(m[1])+parseInt(m[2]), qr: m[3]};
                                var qs = m[3].match(/(\\d+):(\\d+)/g) || [];
                                qs.forEach(function(q,qi) {
                                    var p=q.split(':');
                                    g['q'+(qi+1)+'h']=parseInt(p[0]);
                                    g['q'+(qi+1)+'a']=parseInt(p[1]);
                                });
                                return JSON.stringify(g);
                            }
                        }
                    }
                }
                return null;
                """)
                if raw:
                    g = json.loads(raw)
                    db.execute("""INSERT OR IGNORE INTO games
                        (game_id, home_team, away_team, home_score, away_score, total_score,
                         q1_home, q1_away, q2_home, q2_away, q3_home, q3_away, q4_home, q4_away,
                         status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'final')""",
                        (gid_str, g['home'], g['away'], g['hs'], g['as'], g['t'],
                         g.get('q1h'), g.get('q1a'), g.get('q2h'), g.get('q2a'),
                         g.get('q3h'), g.get('q3a'), g.get('q4h'), g.get('q4a')))
                    saved += 1
                    if saved % 20 == 0:
                        db.commit()
                        print(f"  [{saved}] #{gid_str}: {g['home']} {g['hs']}-{g['as']} {g['away']} = {g['t']}")
            except Exception:
                pass
        db.commit()

    # Stats
    total = db.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    print(f"\n{'='*60}")
    print(f"TOTAL IN DB: {total} games")
    if total > 0:
        stats = db.execute("""SELECT COUNT(*), ROUND(AVG(total_score),1), MIN(total_score), MAX(total_score),
            ROUND(AVG(home_score),1), ROUND(AVG(away_score),1),
            ROUND(AVG(q1_home+q1_away),1), ROUND(AVG(q2_home+q2_away),1),
            ROUND(AVG(q3_home+q3_away),1), ROUND(AVG(q4_home+q4_away),1)
            FROM games WHERE total_score > 0""").fetchone()
        print(f"  Avg Total: {stats[1]}, Min: {stats[2]}, Max: {stats[3]}")
        print(f"  Avg Home: {stats[4]}, Avg Away: {stats[5]}")
        print(f"  Q1 avg: {stats[6]}, Q2 avg: {stats[7]}, Q3 avg: {stats[8]}, Q4 avg: {stats[9]}")

        dist = db.execute("""SELECT
            CASE WHEN total_score < 180 THEN '<180'
                 WHEN total_score < 190 THEN '180-189'
                 WHEN total_score < 200 THEN '190-199'
                 WHEN total_score < 210 THEN '200-209'
                 WHEN total_score < 220 THEN '210-219'
                 WHEN total_score < 230 THEN '220-229'
                 WHEN total_score < 240 THEN '230-239'
                 WHEN total_score < 250 THEN '240-249'
                 ELSE '250+' END as bucket, COUNT(*)
            FROM games GROUP BY bucket ORDER BY bucket""").fetchall()
        print(f"\n  Score Distribution:")
        for b, c in dist:
            bar = '#' * min(c, 60)
            print(f"    {b:>8}: {c:>4} {bar}")

except Exception as e:
    print(f"[FATAL] {e}")
    import traceback
    traceback.print_exc()
finally:
    driver.quit()
    db.close()
    print("\n[DONE]")
