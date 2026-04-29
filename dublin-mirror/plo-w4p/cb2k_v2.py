#!/usr/bin/env python3
"""CB2K v2 - Handle BetConstruct custom dropdowns on results page."""
import json, time, re, sqlite3, os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

DB = '/tmp/blm.db'

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
if not driver: driver = webdriver.Chrome(options=opts)
print("[OK] Chrome")

db = sqlite3.connect(DB)
db.execute("PRAGMA journal_mode=WAL")
db.executescript("""CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT, game_id TEXT UNIQUE NOT NULL,
    league TEXT DEFAULT 'Cyber Basketball 2K26',
    home_team TEXT NOT NULL, away_team TEXT NOT NULL,
    home_score INTEGER, away_score INTEGER, total_score INTEGER,
    q1_home INTEGER, q1_away INTEGER, q2_home INTEGER, q2_away INTEGER,
    q3_home INTEGER, q3_away INTEGER, q4_home INTEGER, q4_away INTEGER,
    ot_home INTEGER, ot_away INTEGER,
    status TEXT DEFAULT 'final', game_date TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);""")
db.commit()

try:
    driver.get('https://www.pokerbet.co.za/en/sports/pre-match/results')
    time.sleep(6)

    # Map the custom dropdown UI
    ui = driver.execute_script("""
    var r = {dropdowns: [], texts: [], inputs: []};

    // BetConstruct custom dropdowns: look for elements that act as selects
    document.querySelectorAll('[class*="dropdown"], [class*="select"], [class*="filter"]').forEach(function(el) {
        r.dropdowns.push({
            cls: el.className.substring(0, 120),
            text: el.textContent.trim().substring(0, 200),
            tag: el.tagName,
            childCount: el.children.length,
            rect: el.getBoundingClientRect()
        });
    });

    // Find all inputs
    document.querySelectorAll('input').forEach(function(inp) {
        r.inputs.push({
            cls: inp.className.substring(0, 80),
            type: inp.getAttribute('type') || '',
            value: inp.value,
            placeholder: inp.placeholder || '',
            id: inp.id || ''
        });
    });

    // Page text focused on filter area
    var filterArea = document.body.innerText.substring(0, 4000);
    r.pageLines = filterArea.split('\\n').filter(l => l.trim().length > 0).slice(0, 50);

    return JSON.stringify(r);
    """)
    data = json.loads(ui)

    print(f"\n[DROPDOWNS] {len(data['dropdowns'])}")
    for dd in data['dropdowns'][:15]:
        txt = dd['text'][:80].replace('\n', ' | ')
        print(f"  [{dd['tag']}] cls={dd['cls'][:60]}  text='{txt}'")

    print(f"\n[INPUTS] {len(data['inputs'])}")
    for inp in data['inputs'][:10]:
        print(f"  type={inp['type']} cls={inp['cls'][:40]} val={inp['value']} ph={inp['placeholder']}")

    print(f"\n[PAGE LINES]")
    for line in data['pageLines'][:30]:
        print(f"  {line}")

    # Step 2: Interact with filters - look for Sport/Competition selectors
    result = driver.execute_script("""
    return new Promise(async (resolve) => {
        var log = [];

        // Look for the "Sport" labeled dropdown - it's usually a custom component
        // In BetConstruct, results filter uses: results-filter-item-bc
        var filterItems = document.querySelectorAll('[class*="results-filter"], [class*="filter-item"]');
        log.push('Filter items: ' + filterItems.length);

        // Try clicking on "Football" text (current sport) to open sport selector
        var sportLabel = null;
        document.querySelectorAll('[class*="results-filter"] [class*="label"], [class*="filter"] span, [class*="filter"] p').forEach(function(el) {
            var t = el.textContent.trim();
            if (t === 'Football' || t === 'Sport' || t === 'Basketball') {
                sportLabel = el;
                log.push('Found sport element: "' + t + '" ' + el.className.substring(0, 50));
            }
        });

        // Click on the Sport area to open dropdown
        if (sportLabel) {
            // Click the parent (which is likely the dropdown trigger)
            var trigger = sportLabel.closest('[class*="dropdown"]') || sportLabel.closest('[class*="select"]') || sportLabel.parentElement;
            if (trigger) {
                trigger.click();
                log.push('Clicked sport trigger');
                await new Promise(r => setTimeout(r, 1000));

                // Now look for dropdown options
                var options = document.querySelectorAll('[class*="dropdown-option"], [class*="dropdown-item"], [class*="option"], [class*="menu-item"]');
                log.push('Options after click: ' + options.length);
                options.forEach(function(opt) {
                    log.push('  opt: ' + opt.textContent.trim().substring(0, 60));
                    if (opt.textContent.trim().toLowerCase().includes('basketball')) {
                        opt.click();
                        log.push('Clicked Basketball option');
                    }
                });
            }
        }

        // More generic: find all text containing 'Football' and click to change
        if (!sportLabel) {
            var allEls = document.querySelectorAll('*');
            for (var i = 0; i < allEls.length; i++) {
                var el = allEls[i];
                if (el.children.length === 0 && el.textContent.trim() === 'Football') {
                    log.push('Found "Football" text element: ' + el.tagName + ' ' + el.className.substring(0, 50));
                    el.click();
                    await new Promise(r => setTimeout(r, 1000));
                    // Check for opened dropdown
                    var openDDs = document.querySelectorAll('[class*="open"], [class*="active"], [class*="expanded"]');
                    log.push('Opened elements: ' + openDDs.length);
                    break;
                }
            }
        }

        await new Promise(r => setTimeout(r, 2000));

        // After selecting Basketball, check for SHOW button and competitions
        var pageText = document.body.innerText;
        log.push('Page has cyber: ' + pageText.toLowerCase().includes('cyber'));
        log.push('Page has basketball: ' + pageText.toLowerCase().includes('basketball'));

        // Look for SHOW/APPLY button
        var buttons = document.querySelectorAll('button, [role="button"], [class*="btn"]');
        buttons.forEach(function(btn) {
            var t = btn.textContent.trim().toUpperCase();
            if (t === 'SHOW' || t === 'APPLY' || t === 'SEARCH') {
                log.push('Found button: ' + t);
                btn.click();
                log.push('Clicked ' + t);
            }
        });

        await new Promise(r => setTimeout(r, 4000));

        // Parse whatever results are showing
        var games = [];
        var text = document.body.innerText;
        var lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

        for (var i = 0; i < lines.length - 2; i++) {
            if (lines[i].toLowerCase().includes('cyber')) {
                for (var j = i + 1; j < Math.min(i + 4, lines.length); j++) {
                    if (lines[j].toLowerCase().includes('cyber') && j > i) {
                        // Found two team lines
                        for (var k = j + 1; k < Math.min(j + 3, lines.length); k++) {
                            var sm = lines[k].match(/(\\d+)\\s*:\\s*(\\d+)\\s*\\((.+)\\)/);
                            if (sm) {
                                var g = {
                                    home: lines[i], away: lines[j],
                                    hs: parseInt(sm[1]), as: parseInt(sm[2]),
                                    t: parseInt(sm[1]) + parseInt(sm[2]),
                                    qr: sm[3]
                                };
                                var qs = sm[3].match(/(\\d+):(\\d+)/g) || [];
                                qs.forEach(function(q, qi) {
                                    var p = q.split(':');
                                    g['q' + (qi+1) + 'h'] = parseInt(p[0]);
                                    g['q' + (qi+1) + 'a'] = parseInt(p[1]);
                                });
                                games.push(g);
                                i = k;
                                break;
                            }
                        }
                        break;
                    }
                }
            }
        }

        log.push('Games found: ' + games.length);
        resolve(JSON.stringify({log: log, games: games}));
    });
    """)

    data = json.loads(result)
    print("\n[LOG]")
    for l in data.get('log', []):
        print(f"  {l}")

    games = data.get('games', [])
    print(f"\n[GAMES] {len(games)}")

    saved = 0
    for g in games:
        gid = f"cb2k_{hash(g['home']+g['away']+str(g['hs'])+str(g['as'])) % 10**8}"
        try:
            db.execute("""INSERT OR IGNORE INTO games
                (game_id, home_team, away_team, home_score, away_score, total_score,
                 q1_home, q1_away, q2_home, q2_away, q3_home, q3_away, q4_home, q4_away,
                 status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'final')""",
                (gid, g['home'], g['away'], g['hs'], g['as'], g['t'],
                 g.get('q1h'), g.get('q1a'), g.get('q2h'), g.get('q2a'),
                 g.get('q3h'), g.get('q3a'), g.get('q4h'), g.get('q4a')))
            saved += 1
            print(f"  [{saved}] {g['home']} {g['hs']}-{g['as']} {g['away']} = {g['t']}")
        except: pass
    db.commit()
    print(f"\n[SAVED] {saved}")

    # Stats
    total = db.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    if total:
        s = db.execute("""SELECT COUNT(*), ROUND(AVG(total_score),1), MIN(total_score), MAX(total_score),
            ROUND(AVG(home_score),1), ROUND(AVG(away_score),1)
            FROM games WHERE total_score > 0""").fetchone()
        print(f"\n  DB: {s[0]} games, Avg={s[1]}, Min={s[2]}, Max={s[3]}, Home={s[4]}, Away={s[5]}")

except Exception as e:
    print(f"[ERR] {e}")
    import traceback; traceback.print_exc()
finally:
    driver.quit(); db.close()
    print("[DONE]")
