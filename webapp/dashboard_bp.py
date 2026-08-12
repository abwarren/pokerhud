"""Dashboard blueprint — MTT schedule/players/pulse + extension hud-sync.

Routes moved verbatim from dashboard.py; credentials reuse the canonical
mtt.db pattern (env MTT_* + ~/.pokerhud_pgpass). No secrets in source.
"""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, request
from flask import current_app as app

from mtt import db as mtt_db

dashboard_bp = Blueprint("dashboard", __name__)

MTT_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>MTT HUD</title>
<style>
body{background:#0d1117;color:#c9d1d9;font-family:system-ui,sans-serif;margin:0;padding:16px}
h1{font-size:18px;border-bottom:1px solid #21262d;padding-bottom:8px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #21262d}
th{color:#8b949e;font-weight:600}
.status-running{color:#3fb950}.status-latereg{color:#d29922}.status-registration{color:#58a6ff}.status-completed{color:#8b949e}
.pulse{display:flex;gap:24px;margin:12px 0;flex-wrap:wrap}
.pulse div{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:10px 16px}
.pulse b{display:block;font-size:22px;color:#3fb950}
</style></head><body>
<h1>MTT HUD — PokerBet + SunBet</h1>
<div style="margin:10px 0"><label for="site">Site</label>
<select id="site">
<option value="all">All</option>
<option value="pokerbet">PokerBet</option>
<option value="sunbet">SunBet</option>
</select></div>
<div class="pulse" id="pulse"></div>
<div id="content"><p>Loading…</p></div>
<script>
const $=id=>document.getElementById(id);
async function load(){
  const site=($('site')&&$('site').value)||'all';
  const q=site==='all'?'':'?site='+encodeURIComponent(site);
  const [sched,pulse]=await Promise.all([
    fetch('/api/schedule'+q).then(r=>r.json()),
    fetch('/api/pulse').then(r=>r.json()),
  ]);
  $('pulse').innerHTML=`<div><b>${pulse.tournaments||0}</b>tournaments</div>
    <div><b>${pulse.players||0}</b>players</div>
    <div><b>${pulse.hands||0}</b>hands</div>`;
  const rows=(sched.tournaments||sched||[]).map(t=>`<tr>
    <td>${t.name||''}</td><td>${t.site||''}</td><td>${t.buyin||''}</td>
    <td>${t.guarantee||''}</td><td>${t.cohort||''}</td>
    <td class="status-${(t.status||'').toLowerCase().replace(/\\s+/g,'')}">${t.status||''}</td></tr>`).join('');
  $('content').innerHTML=`<table><thead><tr><th>Name</th><th>Site</th><th>Buy-in</th><th>GTD</th><th>Cohort</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
}
$('site').addEventListener('change',load);
load();setInterval(load,30000);
</script></body></html>"""


def _get_conn():
    return mtt_db.connect()


@dashboard_bp.get("/")
def index():
    return MTT_HTML


@dashboard_bp.get("/api/schedule")
def schedule():
    try:
        site = (request.args.get("site", "all") or "all").strip().lower()
        sql = ("SELECT name, site, buyin, guarantee, cohort, status, start_time "
               "FROM mtt.tournaments WHERE status <> 'completed'")
        params = []
        if site in ("pokerbet", "sunbet"):
            sql += " AND site = %s"
            params.append(site)
        sql += (" ORDER BY CASE status WHEN 'running' THEN 0 WHEN 'late registration' THEN 1 "
                "WHEN 'registration' THEN 2 ELSE 3 END, start_time LIMIT 200")
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
        return jsonify({"tournaments": rows})
    except Exception as e:
        app.logger.warning("[SCHEDULE] %s", e)
        return jsonify({"error": str(e)}), 500


@dashboard_bp.get("/api/players")
def players():
    try:
        site = (request.args.get("site", "all") or "all").strip().lower()
        sql = ("SELECT site, display_name, normalized_name, count(*) AS tournaments "
               "FROM mtt.players")
        params = []
        if site in ("pokerbet", "sunbet"):
            sql += " WHERE site = %s"
            params.append(site)
        sql += (" GROUP BY site, display_name, normalized_name "
                "ORDER BY tournaments DESC LIMIT 200")
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
        return jsonify({"players": rows})
    except Exception as e:
        app.logger.warning("[PLAYERS] %s", e)
        return jsonify({"error": str(e)}), 500


@dashboard_bp.get("/api/players/<name>")
def player(name):
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT p.site, p.display_name, t.cohort, t.name AS tournament, "
            "pt.finish_position, pt.prize "
            "FROM mtt.players p "
            "JOIN mtt.player_tournaments pt ON pt.player_id = p.id "
            "JOIN mtt.tournaments t ON t.id = pt.tournament_id "
            "WHERE p.normalized_name = %s ORDER BY t.start_time DESC LIMIT 100",
            (name.lower(),))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
        return jsonify({"player": name, "results": rows})
    except Exception as e:
        app.logger.warning("[PLAYER] %s", e)
        return jsonify({"error": str(e)}), 500


@dashboard_bp.get("/api/pulse")
def pulse():
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM mtt.tournaments")
        tournaments = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM mtt.players")
        players = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM mtt.hands")
        hands = cur.fetchone()[0]
        conn.close()
        return jsonify({"tournaments": tournaments, "players": players, "hands": hands})
    except Exception as e:
        app.logger.warning("[PULSE] %s", e)
        return jsonify({"error": str(e)}), 500


@dashboard_bp.post("/api/hud-sync")
def hud_sync():
    """Extension sync — idempotent, never 5xxes (extension ignores failures).

    Writes to public.hud_player_stats only — never touches the mtt schema
    (protects the 85 mtt tests' mtt_test isolation).
    """
    data = request.get_json(silent=True) or {}
    players = data.get("players") or []
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS public.hud_player_stats (
            id SERIAL PRIMARY KEY,
            site TEXT NOT NULL DEFAULT 'pokerbet',
            player_name TEXT NOT NULL,
            observed_on DATE NOT NULL DEFAULT CURRENT_DATE,
            total_hands INT NOT NULL DEFAULT 0,
            stats JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (site, player_name, observed_on))""")
        for p in players:
            stats = {k: v for k, v in p.items() if k not in ("player", "hands")}
            cur.execute("""INSERT INTO public.hud_player_stats
                (site, player_name, total_hands, stats)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (site, player_name, observed_on) DO UPDATE SET
                  total_hands = EXCLUDED.total_hands,
                  stats = EXCLUDED.stats,
                  updated_at = now()""",
                (p.get("site", "pokerbet"), p.get("player"), p.get("hands", 0),
                 json.dumps(stats)))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "received": len(players)})
    except Exception as e:
        app.logger.warning("[HUD-SYNC] %s", e)
        return jsonify({"ok": True, "received": 0, "warning": "db unavailable"})
