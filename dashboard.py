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
.fbar{display:flex;gap:8px;margin-bottom:6px;flex-wrap:wrap;align-items:center}
.fbar input,.fbar select{padding:6px 10px;border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#c9d1d9;font-size:.8rem;outline:none}
.fbar input:focus,.fbar select:focus{border-color:#58a6ff}
.fbar input{flex:1;min-width:180px}
.fbar select{min-width:100px}
.fbar .ct{color:#8b949e;font-size:.75rem;margin-left:auto}
.fbar2{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;align-items:center}
.fbar2 label{color:#8b949e;font-size:.7rem;white-space:nowrap}
.fbar2 input,.fbar2 select{padding:4px 8px;border-radius:4px;border:1px solid #30363d;background:#0d1117;color:#c9d1d9;font-size:.75rem;outline:none;width:70px}
.fbar2 input:focus,.fbar2 select:focus{border-color:#58a6ff}
.ftog{cursor:pointer;color:#58a6ff;font-size:.75rem;margin-bottom:8px;display:inline-block}
.ftog:hover{text-decoration:underline}
.fextra{display:none}
.fextra.show{display:flex}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;padding:8px 12px;border-bottom:2px solid #30363d;color:#8b949e;font-weight:600;white-space:nowrap;cursor:pointer;user-select:none}
th:hover{color:#f0f6fc}
th .arr{color:#58a6ff;margin-left:3px}
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
.tab.active{background:#1f6feb;border-color:#1f6feb;color:#fff}.tab .bc{background:#30363d;border-radius:10px;padding:1px 6px;font-size:.7rem;margin-left:4px}.tab.active .bc{background:#58a6ff33;color:#58a6ff}
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
  <div class="fbar">
    <input id="sched-search" placeholder="Search tournaments..." oninput="renderSchedule()">
    <select id="sched-status" onchange="renderSchedule()">
      <option value="">All Status</option>
      <option value="Running">Running</option>
      <option value="Late Registration">Late Reg</option>
      <option value="Registration">Registration</option>
      <option value="Completed">Completed</option>
    </select>
    <select id="sched-game" onchange="renderSchedule()">
      <option value="">All Games</option>
      <option value="NL Hold'em">NL Hold'em</option>
      <option value="PLO">PLO</option>
    </select>
    <span class="ct" id="sched-count"></span>
  </div>
  <div class="ftog" onclick="document.getElementById('sched-extra').classList.toggle('show')">+ More filters</div>
  <div class="fextra" id="sched-extra">
    <div class="fbar2">
      <label>GTD min</label><input id="sched-gtd-min" placeholder="R" oninput="renderSchedule()">
      <label>GTD max</label><input id="sched-gtd-max" placeholder="R" oninput="renderSchedule()">
      <label>Buy-in min</label><input id="sched-buyin-min" placeholder="R" oninput="renderSchedule()">
      <label>Buy-in max</label><input id="sched-buyin-max" placeholder="R" oninput="renderSchedule()">
      <label>Day</label>
      <select id="sched-day" onchange="renderSchedule()">
        <option value="">All</option>
        <option value="monday">Mon</option><option value="tuesday">Tue</option>
        <option value="wednesday">Wed</option><option value="thursday">Thu</option>
        <option value="friday">Fri</option><option value="saturday">Sat</option>
        <option value="sunday">Sun</option>
      </select>
    </div>
  </div>
  <table>
    <thead><tr>
      <th onclick="sortSchedule('start_time')">Start<span class="arr" id="arr-start_time"></span></th>
      <th onclick="sortSchedule('name')">Tournament<span class="arr" id="arr-name"></span></th>
      <th onclick="sortSchedule('buy_in_total_zar')">Buy-in<span class="arr" id="arr-buy_in_total_zar"></span></th>
      <th onclick="sortSchedule('prize_pool_guaranteed_zar')">GTD<span class="arr" id="arr-prize_pool_guaranteed_zar"></span></th>
      <th>Type</th>
      <th onclick="sortSchedule('players_registered')">Reg<span class="arr" id="arr-players_registered"></span></th>
      <th>Status</th>
    </tr></thead>
    <tbody id="schedule-body"></tbody>
  </table>
</div>

<div id="players-tab" class="content">
  <div class="fbar">
    <input id="play-search" placeholder="Search players..." oninput="renderPlayers()">
    <select id="play-minh" onchange="renderPlayers()">
      <option value="0">Min Hands</option>
      <option value="10">10+</option>
      <option value="25">25+</option>
      <option value="50">50+</option>
      <option value="100">100+</option>
      <option value="200">200+</option>
      <option value="500">500+</option>
    </select>
    <span class="ct" id="play-count"></span>
  </div>
  <div class="ftog" onclick="document.getElementById('play-extra').classList.toggle('show')">+ More filters</div>
  <div class="fextra" id="play-extra">
    <div class="fbar2">
      <label>VPIP ≥</label><input id="play-vpip-min" placeholder="%" oninput="renderPlayers()">
      <label>VPIP ≤</label><input id="play-vpip-max" placeholder="%" oninput="renderPlayers()">
      <label>PFR ≥</label><input id="play-pfr-min" placeholder="%" oninput="renderPlayers()">
      <label>PFR ≤</label><input id="play-pfr-max" placeholder="%" oninput="renderPlayers()">
      <label>3B ≥</label><input id="play-3b-min" placeholder="%" oninput="renderPlayers()">
      <label>3B ≤</label><input id="play-3b-max" placeholder="%" oninput="renderPlayers()">
      <label>AF ≥</label><input id="play-af-min" oninput="renderPlayers()">
      <label>AF ≤</label><input id="play-af-max" oninput="renderPlayers()">
      <label>Monotone ≥</label><input id="play-mon-min" placeholder="%P" oninput="renderPlayers()">
      <label>SPR ≤</label><input id="play-spr-max" oninput="renderPlayers()">
    </div>
  </div>
  <table>
    <thead><tr>
      <th onclick="sortPlayers('player')">Player<span class="arr" id="arr-player"></span></th>
      <th onclick="sortPlayers('hands')">H<span class="arr" id="arr-hands"></span></th>
      <th onclick="sortPlayers('vpip')">VPIP<span class="arr" id="arr-vpip"></span></th>
      <th onclick="sortPlayers('pfr')">PFR<span class="arr" id="arr-pfr"></span></th>
      <th onclick="sortPlayers('three_bet')">3B<span class="arr" id="arr-three_bet"></span></th>
      <th onclick="sortPlayers('af')">AF<span class="arr" id="arr-af"></span></th>
      <th title="Bet sizing % pot per street">P♠</th><th>F♠</th><th>T♠</th><th>R♠</th>
      <th title="Flop bet sizing by board texture">Texture</th>
      <th>SPR</th>
    </tr></thead>
    <tbody id="players-body"></tbody>
  </table>
</div>

<script>
const API='/api/';
let scheduleData = [];
let players = [];
let schedSort = {key:'status',dir:1};
let playSort = {key:'hands',dir:-1};

function fmtP(v){return v!=null&&v!==undefined?Number(v).toFixed(1):'?'}
function fmtVP(v){return v!=null&&v!==undefined?Number(v).toFixed(1)+'%':'?'}
function gv(o,k){let v=o[k];return v!=null?Number(v):null}

function getVal(o,k){
  let v=o[k];
  if(v===null||v===undefined) return k==='player'?'zzz':-1e9;
  if(typeof v==='string') return v.toLowerCase();
  return v;
}

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
    scheduleData=d;
    renderSchedule();
  }catch(e){}
}

function renderSchedule(){
  let d=scheduleData;
  const q=document.getElementById('sched-search').value.toLowerCase();
  const st=document.getElementById('sched-status').value;
  const gt=document.getElementById('sched-game').value;
  const gtdMin=parseFloat(document.getElementById('sched-gtd-min').value)||0;
  const gtdMax=parseFloat(document.getElementById('sched-gtd-max').value)||0;
  const buyMin=parseFloat(document.getElementById('sched-buyin-min').value)||0;
  const buyMax=parseFloat(document.getElementById('sched-buyin-max').value)||0;
  const day=document.getElementById('sched-day').value.toLowerCase();

  let filtered=d.filter(t=>{
    if(q && !t.name.toLowerCase().includes(q)) return false;
    if(st && t.status!==st) return false;
    if(gt && t.game_type!==gt) return false;
    if(gtdMin>0 && (!t.prize_pool_guaranteed_zar||t.prize_pool_guaranteed_zar<gtdMin)) return false;
    if(gtdMax>0 && (!t.prize_pool_guaranteed_zar||t.prize_pool_guaranteed_zar>gtdMax)) return false;
    if(buyMin>0 && (!t.buy_in_total_zar||t.buy_in_total_zar<buyMin)) return false;
    if(buyMax>0 && (!t.buy_in_total_zar||t.buy_in_total_zar>buyMax)) return false;
    if(day){
      const nameL=t.name.toLowerCase();
      const dayMap={'monday':['mon','monday'],'tuesday':['tue','tuesday'],'wednesday':['wed','wacky','wednesday'],
                    'thursday':['thu','thursday'],'friday':['fri','friday'],'saturday':['sat','saturday'],'sunday':['sun','slam','sunday']};
      const keywords=dayMap[day]||[day];
      if(!keywords.some(k=>nameL.includes(k))) return false;
    }
    return true;
  });

  filtered.sort((a,b)=>{
    let va=getVal(a,schedSort.key), vb=getVal(b,schedSort.key);
    if(typeof va==='string') return (va<vb?-1:1)*schedSort.dir;
    return ((va||0)-(vb||0))*schedSort.dir;
  });

  document.getElementById('sched-count').textContent=filtered.length+'/'+d.length;

  const tbody=document.getElementById('schedule-body');
  tbody.innerHTML=filtered.map(t=>{
    const statusClass={Registration:'badge-reg','Late Registration':'badge-late',Running:'badge-run',Completed:'badge-done'}[t.status]||'badge-reg';
    const buyin=t.buy_in_total_zar?'R'+Number(t.buy_in_total_zar).toLocaleString():'-';
    const gtd=t.prize_pool_guaranteed_zar?'R'+Number(t.prize_pool_guaranteed_zar).toLocaleString():'-';
    const reg=t.players_registered?(t.players_max?t.players_registered+'/'+t.players_max:t.players_registered):'-';
    return '<tr><td>'+(t.start_time||'-')+'</td><td>'+t.name+'</td><td>'+buyin+'</td><td>'+gtd+'</td><td>'+(t.game_type||'NLH')+'</td><td>'+reg+'</td><td><span class="badge '+statusClass+'">'+(t.status||'?')+'</span></td></tr>'
  }).join('');
}

function sortSchedule(key){
  if(schedSort.key===key) schedSort.dir*=-1;
  else {schedSort.key=key; schedSort.dir=1}
  document.querySelectorAll('#schedule-tab .arr').forEach(e=>e.textContent='');
  const el=document.getElementById('arr-'+key);
  if(el) el.textContent=schedSort.dir>0?'▲':'▼';
  renderSchedule();
}

async function loadPlayers(){
  try{
    const r=await fetch(API+'players'); const d=await r.json();
    if(d.error){document.getElementById('players-body').innerHTML='<tr><td colspan="12">'+d.error+'</td></tr>';return}
    players=d;
    renderPlayers();
  }catch(e){}
}

function renderPlayers(){
  let d=players;
  const q=document.getElementById('play-search').value.toLowerCase();
  const mh=parseInt(document.getElementById('play-minh').value)||0;
  const vpipMin=parseFloat(document.getElementById('play-vpip-min').value);
  const vpipMax=parseFloat(document.getElementById('play-vpip-max').value);
  const pfrMin=parseFloat(document.getElementById('play-pfr-min').value);
  const pfrMax=parseFloat(document.getElementById('play-pfr-max').value);
  const b3Min=parseFloat(document.getElementById('play-3b-min').value);
  const b3Max=parseFloat(document.getElementById('play-3b-max').value);
  const afMin=parseFloat(document.getElementById('play-af-min').value);
  const afMax=parseFloat(document.getElementById('play-af-max').value);
  const monMin=parseFloat(document.getElementById('play-mon-min').value);
  const sprMax=parseFloat(document.getElementById('play-spr-max').value);

  let filtered=d.filter(p=>{
    if(q && !p.player.toLowerCase().includes(q)) return false;
    if(mh>0 && (p.hands||0)<mh) return false;
    if(!isNaN(vpipMin)&&(p.vpip===undefined||p.vpip===null||p.vpip<vpipMin)) return false;
    if(!isNaN(vpipMax)&&(p.vpip===undefined||p.vpip===null||p.vpip>vpipMax)) return false;
    if(!isNaN(pfrMin)&&(p.pfr===undefined||p.pfr===null||p.pfr<pfrMin)) return false;
    if(!isNaN(pfrMax)&&(p.pfr===undefined||p.pfr===null||p.pfr>pfrMax)) return false;
    if(!isNaN(b3Min)&&(p.three_bet===undefined||p.three_bet===null||p.three_bet<b3Min)) return false;
    if(!isNaN(b3Max)&&(p.three_bet===undefined||p.three_bet===null||p.three_bet>b3Max)) return false;
    if(!isNaN(afMin)&&(p.af===undefined||p.af===null||p.af<afMin)) return false;
    if(!isNaN(afMax)&&(p.af===undefined||p.af===null||p.af>afMax)) return false;
    if(!isNaN(monMin)&&(p.avg_monotone_pot_pct===undefined||p.avg_monotone_pot_pct===null||p.avg_monotone_pot_pct<monMin)) return false;
    if(!isNaN(sprMax)&&(p.avg_spr===undefined||p.avg_spr===null||p.avg_spr>sprMax)) return false;
    return true;
  });

  filtered.sort((a,b)=>{
    let va=getVal(a,playSort.key), vb=getVal(b,playSort.key);
    if(typeof va==='string') return (va<vb?-1:1)*playSort.dir;
    return ((va||0)-(vb||0))*playSort.dir;
  });

  document.getElementById('play-count').textContent=filtered.length+'/'+d.length;

  const tbody=document.getElementById('players-body');
  if(!filtered.length){tbody.innerHTML='<tr><td colspan="12">No data collected yet. Scraper running every 30 min.</td></tr>';return}
  tbody.innerHTML=filtered.map(p=>{
    return '<tr class="player-row">'+
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
}

function sortPlayers(key){
  if(playSort.key===key) playSort.dir*=-1;
  else {playSort.key=key; playSort.dir=-1}
  document.querySelectorAll('#players-tab .arr').forEach(e=>e.textContent='');
  const el=document.getElementById('arr-'+key);
  if(el) el.textContent=playSort.dir>0?'▲':'▼';
  renderPlayers();
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
