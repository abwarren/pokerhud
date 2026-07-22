#!/usr/bin/env python3
"""MTT Stats Dashboard — 10K+ Tournament HUD"""
import json
from datetime import datetime, timezone
from flask import Flask, jsonify, Response
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from pathlib import Path

app = Flask(__name__)
CORS(app)

DB = dict(host='localhost', port=5432, database='pokerhud',
          user='warren', password='Gemm@143')
SCRAPED = Path(__file__).parent / 'scraped_data' / 'high_rollers'


def get_conn():
    return psycopg2.connect(**DB)


# ── API Routes ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return Response(HTML, content_type='text/html')


@app.route('/api/schedule')
def schedule():
    """Upcoming & active 10K+ tournaments from DB."""
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, name, buy_in_entry_zar, buy_in_fee_zar,
                   buy_in_total_zar, prize_pool_guaranteed_zar,
                   start_time, game_type, status, players_registered,
                   players_max, is_satellite, scraped_at
            FROM tournaments
            WHERE prize_pool_guaranteed_zar >= 10000
               OR buy_in_total_zar >= 10000
            ORDER BY
                CASE status
                    WHEN 'Running' THEN 0
                    WHEN 'Late Registration' THEN 1
                    WHEN 'Registration' THEN 2
                    ELSE 3
                END,
                start_time DESC NULLS LAST
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/players')
def players():
    """Aggregate player stats across all 10K+ tournaments."""
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT u.primary_name AS player,
                   u.total_hands AS hands,
                   u.aggregate_stats,
                   u.positional_stats,
                   u.last_seen
            FROM unified_players u
            WHERE u.total_hands > 0
            ORDER BY u.total_hands DESC
            LIMIT 100
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        result = []
        for r in rows:
            p = {'player': r['player'], 'hands': r['hands']}
            ag = r.get('aggregate_stats') or {}
            if isinstance(ag, str):
                ag = json.loads(ag)
            for k in ('vpip', 'pfr', 'three_bet', 'af', 'wtsd', 'won_at_sd',
                      'avg_bet_pot_pct', 'avg_spr',
                      'avg_preflop_pot_pct', 'avg_flop_pot_pct',
                      'avg_turn_pot_pct', 'avg_river_pot_pct',
                      'avg_monotone_pot_pct', 'avg_paired_pot_pct', 'avg_rainbow_pot_pct'):
                if k in ag:
                    p[k] = ag[k]
            result.append(p)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/players/<name>')
def player_detail(name):
    """Per-player detail with timeline."""
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT u.primary_name, u.total_hands,
                   u.aggregate_stats, u.positional_stats,
                   u.last_seen, u.updated_at
            FROM unified_players u
            WHERE LOWER(u.primary_name) = LOWER(%s)
        """, (name,))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'player not found'}), 404
        cur.close()
        conn.close()
        p = dict(row)
        for f in ('aggregate_stats', 'positional_stats'):
            if isinstance(p.get(f), str):
                p[f] = json.loads(p[f])
        return jsonify(p)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pulse')
def pulse():
    """Scraper health & data volume."""
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT count(*) as total_tournaments FROM tournaments WHERE prize_pool_guaranteed_zar >= 10000")
        t = cur.fetchone()
        cur.execute("SELECT count(*) as total_players FROM unified_players WHERE total_hands > 0")
        p = cur.fetchone()
        cur.execute("SELECT count(*) as total_hands FROM hands")
        h = cur.fetchone()
        cur.execute("SELECT scraped_at FROM tournaments ORDER BY scraped_at DESC LIMIT 1")
        last = cur.fetchone()
        cur.close()
        conn.close()
        files = list(SCRAPED.glob('*.json')) if SCRAPED.exists() else []
        return jsonify({
            'tournaments': t['total_tournaments'],
            'players': p['total_players'],
            'hands': h['total_hands'],
            'data_files': len(files),
            'last_scrape': last['scraped_at'].isoformat() if last else None,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── HTML Frontend ────────────────────────────────────────────────────────────

HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MTT HUD — 10K+ PokerBet</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}
h1{font-size:1.5rem;margin-bottom:4px;color:#f0f6fc}
.sub{color:#8b949e;font-size:.85rem;margin-bottom:20px}
.grid{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px;margin-bottom:24px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}
.card .val{font-size:1.8rem;font-weight:600;color:#58a6ff}
.card .lbl{font-size:.8rem;color:#8b949e;margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;padding:8px 12px;border-bottom:2px solid #30363d;color:#8b949e;font-weight:600;white-space:nowrap}
td{padding:8px 12px;border-bottom:1px solid #21262d}
tr:hover{background:#1c2128}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.75rem;font-weight:600}
.badge-reg{background:#1f6feb33;color:#58a6ff}
.badge-run{background:#23863633;color:#3fb950}
.badge-late{background:#d2992233;color:#d29922}
.badge-done{background:#30363d;color:#8b949e}
.player-row{cursor:pointer}
.player-expand{display:none;background:#0d1117;padding:12px 16px;margin:4px 0 8px;border-radius:6px;font-size:.8rem}
.player-expand.show{display:block}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin-top:8px}
.stat-item{text-align:center;padding:6px;background:#161b22;border-radius:4px}
.stat-item .sv{font-size:1.1rem;font-weight:600;color:#f0f6fc}
.stat-item .sl{font-size:.7rem;color:#8b949e}
.tabs{display:flex;gap:4px;margin-bottom:16px}
.tab{padding:8px 16px;border-radius:6px;cursor:pointer;font-size:.85rem;background:#161b22;border:1px solid #30363d}
.tab.active{background:#1f6feb;border-color:#1f6feb;color:#fff}
.content{display:none}
.content.active{display:block}
@media(max-width:768px){.grid{grid-template-columns:1fr 1fr}}
</style>
</head>
<body>
<h1> MTTHUD — 10K+ PokerBet</h1>
<div class="sub" id="last-scraped">Awaiting data...</div>

<div class="grid" id="pulse-grid">
  <div class="card"><div class="val" id="p-tourneys">-</div><div class="lbl">Tournaments Tracked</div></div>
  <div class="card"><div class="val" id="p-players">-</div><div class="lbl">Players Scouted</div></div>
  <div class="card"><div class="val" id="p-hands">-</div><div class="lbl">Hands Collected</div></div>
  <div class="card"><div class="val" id="p-files">-</div><div class="lbl">Data Files</div></div>
</div>

<div class="tabs">
  <div class="tab active" onclick="switchTab('schedule')">Schedule</div>
  <div class="tab" onclick="switchTab('players')">Players</div>
</div>

<div id="schedule-tab" class="content active">
  <table>
    <thead><tr>
      <th>Start</th><th>Tournament</th><th>Buy-in</th><th>GTD</th><th>Type</th><th>Reg</th><th>Status</th>
    </tr></thead>
    <tbody id="schedule-body"></tbody>
  </table>
</div>

<div id="players-tab" class="content">
  <table>
    <thead><tr>
      <th>Player</th><th>H</th><th>VPIP</th><th>PFR</th><th>3B</th><th>AF</th>
      <th title="Bet sizing % pot per street">P♠</th><th>F♠</th><th>T♠</th><th>R♠</th>
      <th title="Flop bet sizing by board texture">Texture</th><th>SPR</th>
    </tr></thead>
    <tbody id="players-body"></tbody>
  </table>
</div>

<script>
const API='/api/';
let players = [];

function fmtP(v){return v!=null&&v!==undefined?Number(v).toFixed(1):'?'}
function fmtVP(v){return v!=null&&v!==undefined?Number(v).toFixed(1)+'%':'?'}

async function loadPulse(){
  try{
    const r=await fetch(API+'pulse'); const d=await r.json();
    document.getElementById('p-tourneys').textContent=d.tournaments??'-';
    document.getElementById('p-players').textContent=d.players??'-';
    document.getElementById('p-hands').textContent=d.hands??'-';
    document.getElementById('p-files').textContent=d.data_files??'-';
    if(d.last_scrape) document.getElementById('last-scraped').textContent='Last scrape: '+new Date(d.last_scrape).toLocaleString();
  }catch(e){}
}

async function loadSchedule(){
  try{
    const r=await fetch(API+'schedule'); const d=await r.json();
    if(d.error){document.getElementById('schedule-body').innerHTML='<tr><td colspan="7">'+d.error+'</td></tr>';return}
    const tbody=document.getElementById('schedule-body');
    tbody.innerHTML=d.map(t=>{
      const statusClass={Registration:'badge-reg','Late Registration':'badge-late',Running:'badge-run',Completed:'badge-done'}[t.status]||'badge-reg';
      const buyin=t.buy_in_total_zar?'R'+Number(t.buy_in_total_zar).toLocaleString():'-';
      const gtd=t.prize_pool_guaranteed_zar?'R'+Number(t.prize_pool_guaranteed_zar).toLocaleString():'-';
      const reg=t.players_registered?(t.players_max?t.players_registered+'/'+t.players_max:t.players_registered):'-';
      return '<tr><td>'+(t.start_time||'-')+'</td><td>'+t.name+'</td><td>'+buyin+'</td><td>'+gtd+'</td><td>'+(t.game_type||'NLH')+'</td><td>'+reg+'</td><td><span class="badge '+statusClass+'">'+(t.status||'?')+'</span></td></tr>'
    }).join('');
  }catch(e){}
}

async function loadPlayers(){
  try{
    const r=await fetch(API+'players'); const d=await r.json();
    if(d.error){document.getElementById('players-body').innerHTML='<tr><td colspan="11">'+d.error+'</td></tr>';return}
    players=d;
    const tbody=document.getElementById('players-body');
    if(!players.length){tbody.innerHTML='<tr><td colspan="11">No data collected yet. Scraper running every 30 min.</td></tr>';return}
    tbody.innerHTML=players.map(p=>{
      return '<tr class="player-row" onclick="togglePlayer('+(players.indexOf(p))+')">'+
        '<td><strong>'+p.player+'</strong></td>'+
        '<td>'+(p.hands||0)+'</td>'+
        '<td>'+fmtVP(p.vpip)+'</td>'+
        '<td>'+fmtVP(p.pfr)+'</td>'+
        '<td>'+fmtVP(p.three_bet)+'</td>'+
        '<td>'+(p.af!=null?Number(p.af).toFixed(1):'?')+'</td>'+
        '<td>'+fmtP(p.avg_preflop_pot_pct)+'%</td>'+
        '<td>'+fmtP(p.avg_flop_pot_pct)+'%</td>'+
        '<td>'+fmtP(p.avg_turn_pot_pct)+'%</td>'+
        '<td>'+fmtP(p.avg_river_pot_pct)+'%</td>'+
        '<td style="font-size:.75rem">'+
          (p.avg_monotone_pot_pct?'M:'+Number(p.avg_monotone_pot_pct).toFixed(0)+'% ':'')+
          (p.avg_paired_pot_pct?'P:'+Number(p.avg_paired_pot_pct).toFixed(0)+'% ':'')+
          (p.avg_rainbow_pot_pct?'R:'+Number(p.avg_rainbow_pot_pct).toFixed(0)+'%':'')+
        '</td>'+
        '<td>'+(p.avg_spr!=null?Number(p.avg_spr).toFixed(1):'?')+'</td>'+
      '</tr>'
    }).join('');
  }catch(e){}
}

function togglePlayer(idx){
  const p=players[idx];
  console.log('Detail:',p);
}

function switchTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.content').forEach(c=>c.classList.remove('active'));
  document.querySelector('.tab[onclick*="'+name+'"]').classList.add('active');
  document.getElementById(name+'-tab').classList.add('active');
}

loadPulse(); loadSchedule(); loadPlayers();
setInterval(()=>{loadPulse(); loadSchedule();},30000);
</script>
</body>
</html>'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8899, debug=False)
