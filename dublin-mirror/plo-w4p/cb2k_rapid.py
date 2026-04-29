#!/usr/bin/env python3
"""Fast game-ID scanner. Scrapes ~200 games from PokerBet results pages."""
import json, time, re, sqlite3
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import os

DB = '/tmp/blm.db'
URL = 'https://www.pokerbet.co.za/en/sports/pre-match/results?game='

opts = Options()
opts.add_argument('--headless'); opts.add_argument('--no-sandbox')
opts.add_argument('--disable-dev-shm-usage'); opts.add_argument('--disable-gpu')
opts.add_argument('--window-size=1920,1080')
opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
for p in ['/usr/bin/chromedriver', '/usr/local/bin/chromedriver']:
    if os.path.exists(p):
        driver = webdriver.Chrome(service=Service(executable_path=p), options=opts)
        break
print("[OK] Chrome ready")

db = sqlite3.connect(DB)
db.execute("PRAGMA journal_mode=WAL")

JS = """
var lines = document.body.innerText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
var result = null;
for (var i = 0; i < lines.length - 2; i++) {
    if (lines[i].toLowerCase().includes('cyber')) {
        var home = lines[i];
        var away = lines[i+1];
        if (!away || away.toLowerCase().includes('pokerbet') || away.length < 3) continue;
        var scoreMatch = (lines[i+2] || '').match(/(\\d+)\\s*:\\s*(\\d+)\\s*\\((.+)\\)/);
        if (scoreMatch) {
            result = {
                home_team: home, away_team: away,
                home_score: parseInt(scoreMatch[1]),
                away_score: parseInt(scoreMatch[2]),
                total: parseInt(scoreMatch[1]) + parseInt(scoreMatch[2]),
                q_raw: scoreMatch[3]
            };
            var qs = scoreMatch[3].match(/(\\d+):(\\d+)/g) || [];
            qs.forEach(function(q, qi) {
                var p = q.split(':');
                result['q' + (qi+1) + '_h'] = parseInt(p[0]);
                result['q' + (qi+1) + '_a'] = parseInt(p[1]);
            });
            break;
        }
    }
}
return result ? JSON.stringify(result) : null;
"""

# Scan known game IDs - these are sequential
# Game 29585435 and 28744451 are confirmed Cyber Basketball
# Let's scan around 29585435 (most recent) going backward
start = 29585435
saved = 0
misses = 0

# Go backward from latest known
for gid in range(start, start - 5000, -1):
    try:
        driver.get(URL + str(gid))
        time.sleep(1.2)
        raw = driver.execute_script(JS)
        if raw:
            g = json.loads(raw)
            try:
                db.execute("""INSERT OR IGNORE INTO games
                    (game_id, home_team, away_team, home_score, away_score, total_score,
                     q1_home, q1_away, q2_home, q2_away, q3_home, q3_away, q4_home, q4_away,
                     status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'final')""",
                    (str(gid), g['home_team'], g['away_team'],
                     g['home_score'], g['away_score'], g['total'],
                     g.get('q1_h'), g.get('q1_a'), g.get('q2_h'), g.get('q2_a'),
                     g.get('q3_h'), g.get('q3_a'), g.get('q4_h'), g.get('q4_a')))
                db.commit()
                saved += 1
                misses = 0
                if saved % 10 == 0 or saved <= 5:
                    print(f"[{saved}] #{gid}: {g['home_team']} {g['home_score']}-{g['away_score']} {g['away_team']} = {g['total']}")
            except Exception as e:
                pass
        else:
            misses += 1
            if misses >= 50:
                print(f"[STOP] 50 consecutive misses at #{gid}")
                break
    except Exception as e:
        misses += 1
        if misses >= 50: break

# Quick stats
print(f"\n{'='*60}")
print(f"SAVED: {saved} games")
rows = db.execute("SELECT COUNT(*), AVG(total_score), MIN(total_score), MAX(total_score), AVG(home_score), AVG(away_score) FROM games WHERE total_score > 0").fetchone()
if rows and rows[0]:
    print(f"  Games: {rows[0]}")
    print(f"  Avg Total: {rows[1]:.1f}, Min: {rows[2]}, Max: {rows[3]}")
    print(f"  Avg Home: {rows[4]:.1f}, Avg Away: {rows[5]:.1f}")

    # Distribution
    dist = db.execute("SELECT CASE WHEN total_score < 190 THEN '<190' WHEN total_score < 200 THEN '190-199' WHEN total_score < 210 THEN '200-209' WHEN total_score < 220 THEN '210-219' WHEN total_score < 230 THEN '220-229' WHEN total_score < 240 THEN '230-239' WHEN total_score < 250 THEN '240-249' ELSE '250+' END as bucket, COUNT(*) FROM games GROUP BY bucket ORDER BY bucket").fetchall()
    print(f"\n  Total Score Distribution:")
    for bucket, count in dist:
        bar = '#' * count
        print(f"    {bucket:>8}: {count:>4} {bar}")

driver.quit()
db.close()
print("\n[DONE]")
