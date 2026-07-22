#!/usr/bin/env python3
"""Time Series Ledger Dashboard for Active Players"""
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import psycopg2
import psycopg2.extras

app = Flask(__name__)
CORS(app)

DB = dict(host='localhost', port=5432, database='pokerhud',
          user='warren', password='Gemm@143')


def get_conn():
    return psycopg2.connect(**DB)


@app.route('/')
def index():
    return Response(DASHBOARD_HTML, content_type='text/html')


@app.route('/api/players')
def players():
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT m.username, m.status, m.container_name, m.eip, m.batch,
                   m.is_active, m.notes,
                   c.balance_zar as latest_balance,
                   c.observed_at as last_seen
            FROM myplayerspokerbet m
            LEFT JOIN LATERAL (
                SELECT balance_zar, observed_at
                FROM cash_balances
                WHERE lower(player_name) = lower(m.username)
                ORDER BY observed_at DESC LIMIT 1
            ) c ON true
            WHERE m.is_active = true
            ORDER BY m.username
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        for r in rows:
            if r.get('last_seen'):
                r['last_seen'] = r['last_seen'].isoformat()
            if r.get('latest_balance') is not None:
                r['latest_balance'] = float(r['latest_balance'])
        return jsonify(rows)
    except Exception:
        return jsonify([])


@app.route('/api/balances')
def balances():
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT lower(player_name) as player_name,
                   balance_zar, delta_zar, observed_at
            FROM cash_balances
            WHERE lower(player_name) IN (
                SELECT lower(username) FROM myplayerspokerbet WHERE is_active = true
            )
            ORDER BY observed_at ASC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        series = {}
        for r in rows:
            name = r['player_name']
            if name not in series:
                series[name] = []
            series[name].append({
                't': r['observed_at'].isoformat(),
                'bal': float(r['balance_zar']),
                'delta': float(r['delta_zar'] or 0)
            })
        return jsonify(series)
    except Exception:
        return jsonify({})


@app.route('/api/hud-sync', methods=['POST'])
def hud_sync():
    """Receive HUD stats from the Chrome extension."""
    data = request.get_json(silent=True) or {}
    if not data or not data.get('players'):
        return jsonify({'ok': True, 'stored': 0})
    stored = 0
    try:
        conn = get_conn()
        cur = conn.cursor()
        for p in data['players']:
            cur.execute("""
                INSERT INTO unified_players (primary_name, total_hands, aggregate_stats, updated_at)
                VALUES (%s, %s, %s::jsonb, now())
                ON CONFLICT (user_id, primary_name) WHERE (user_id IS NULL)
                DO UPDATE SET total_hands = EXCLUDED.total_hands,
                    aggregate_stats = EXCLUDED.aggregate_stats,
                    updated_at = now()
            """, (p.get('name', 'unknown'), p.get('hands', 0), json.dumps(p)))
            stored += 1
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
    return jsonify({'ok': True, 'stored': stored})

@app.route('/api/tournaments')
def tournament_list():
    """Return active/upcoming tournaments from the database."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT name, buy_in_total_zar, prize_pool_guaranteed_zar,
               start_time, game_type, status, players_registered, has_rebuy,
               description
        FROM tournaments
        WHERE status != 'Completed'
        ORDER BY
            CASE status
                WHEN 'Late Registration' THEN 1
                WHEN 'Running' THEN 2
                WHEN 'Registration' THEN 3
                ELSE 4
            END,
            start_time ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    for r in rows:
        for k in ('buy_in_total_zar', 'prize_pool_guaranteed_zar', 'players_registered'):
            if r.get(k) is not None:
                r[k] = float(r[k])
    return jsonify(rows)

@app.route('/api/tenk-tournaments')
def tenk_tournaments():
    """Return all 10K+ guaranteed tournaments."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT name, buy_in_total_zar, prize_pool_guaranteed_zar,
               start_time, game_type, status, players_registered, has_rebuy,
               description
        FROM tournaments
        WHERE prize_pool_guaranteed_zar >= 10000
        ORDER BY prize_pool_guaranteed_zar DESC, start_time ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    for r in rows:
        for k in ('buy_in_total_zar', 'prize_pool_guaranteed_zar', 'players_registered'):
            if r.get(k) is not None:
                r[k] = float(r[k])
    return jsonify(rows)

@app.route('/api/summary')
def summary():
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            WITH ranked AS (
                SELECT lower(player_name) as pn, balance_zar, observed_at,
                       ROW_NUMBER() OVER (PARTITION BY lower(player_name) ORDER BY observed_at ASC) as rn_first,
                       ROW_NUMBER() OVER (PARTITION BY lower(player_name) ORDER BY observed_at DESC) as rn_last
                FROM cash_balances
                WHERE lower(player_name) IN (
                    SELECT lower(username) FROM myplayerspokerbet WHERE is_active = true
                )
            )
            SELECT pn as player_name,
                   COUNT(*) as observations,
                   MIN(balance_zar) as min_bal,
                   MAX(balance_zar) as max_bal,
                   MAX(CASE WHEN rn_first = 1 THEN balance_zar END) as first_bal,
                   MAX(CASE WHEN rn_last = 1 THEN balance_zar END) as last_bal,
                   MIN(observed_at) as first_seen,
                   MAX(observed_at) as last_seen
            FROM ranked
            GROUP BY pn
            ORDER BY pn
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        result = []
        for r in rows:
            first = float(r['first_bal'] or 0)
            last = float(r['last_bal'] or 0)
            result.append({
                'player': r['player_name'],
                'observations': r['observations'],
                'first_bal': first,
                'last_bal': last,
                'pnl': round(last - first, 2),
                'min_bal': float(r['min_bal'] or 0),
                'max_bal': float(r['max_bal'] or 0),
                'first_seen': r['first_seen'].isoformat() if r['first_seen'] else None,
                'last_seen': r['last_seen'].isoformat() if r['last_seen'] else None,
            })
        total_pnl = sum(r['pnl'] for r in result)
        return jsonify({'players': result, 'total_pnl': round(total_pnl, 2)})
    except Exception:
        return jsonify({'players': [], 'total_pnl': 0})


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PLO Player Ledger</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0f1117; color: #e0e0e0; }
.header { background: #1a1d27; padding: 16px 24px; border-bottom: 1px solid #2a2d37;
          display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 20px; color: #fff; }
.header .total { font-size: 18px; font-weight: 600; }
.total.pos { color: #4ade80; } .total.neg { color: #f87171; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 12px; padding: 16px; }
.card { background: #1a1d27; border-radius: 8px; padding: 14px; border: 1px solid #2a2d37; }
.card .name { font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 4px; }
.card .stats { display: flex; gap: 12px; font-size: 12px; color: #9ca3af; margin-bottom: 8px; }
.card .pnl { font-size: 16px; font-weight: 700; }
.pos { color: #4ade80; } .neg { color: #f87171; } .flat { color: #9ca3af; }
.chart-wrap { height: 120px; margin-top: 8px; }
.big-chart { background: #1a1d27; border-radius: 8px; padding: 16px; margin: 16px;
             border: 1px solid #2a2d37; }
.big-chart h2 { font-size: 16px; color: #fff; margin-bottom: 12px; }
.big-chart-wrap { height: 320px; }
table { width: 100%; border-collapse: collapse; margin: 16px; max-width: calc(100% - 32px); }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #2a2d37; font-size: 13px; }
th { color: #9ca3af; font-weight: 500; background: #1a1d27; }
td { color: #e0e0e0; }
.refresh { background: #3b82f6; color: #fff; border: none; padding: 6px 14px;
           border-radius: 4px; cursor: pointer; font-size: 13px; }
.refresh:hover { background: #2563eb; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
.dot-active { background: #4ade80; } .dot-pool { background: #fbbf24; }
</style>
</head>
<body>
<div class="header">
  <h1>PLO Player Ledger — Active Players</h1>
  <div>
    <span class="total" id="totalPnl">Loading...</span>
    <button class="refresh" onclick="load()" style="margin-left:12px">Refresh</button>
  </div>
</div>

<div class="big-chart">
  <h2>All Players — Balance Over Time</h2>
  <div class="big-chart-wrap"><canvas id="allChart"></canvas></div>
</div>

<div class="grid" id="cards"></div>

<div style="padding:0 16px">
  <h2 style="font-size:16px;margin-bottom:8px;color:#fff">Ledger Summary</h2>
</div>
<table id="ledgerTable">
  <thead><tr>
    <th>Player</th><th>First Bal (R)</th><th>Current (R)</th><th>P&L (R)</th>
    <th>Min</th><th>Max</th><th>Obs</th><th>Last Seen</th>
  </tr></thead>
  <tbody id="ledgerBody"></tbody>
</table>

<script>
const COLORS = [
  '#3b82f6','#f59e0b','#10b981','#ef4444','#8b5cf6',
  '#ec4899','#06b6d4','#f97316','#84cc16'
];
let allChart = null;
const miniCharts = {};

async function load() {
  const [sumRes, balRes] = await Promise.all([
    fetch('/api/summary').then(r=>r.json()),
    fetch('/api/balances').then(r=>r.json())
  ]);
  renderTotal(sumRes);
  renderAllChart(balRes);
  renderCards(sumRes.players, balRes);
  renderTable(sumRes.players);
}

function renderTotal(sum) {
  const el = document.getElementById('totalPnl');
  const pnl = sum.total_pnl;
  el.textContent = `Total P&L: R${pnl>=0?'+':''}${pnl.toFixed(2)}`;
  el.className = 'total ' + (pnl>0?'pos':pnl<0?'neg':'flat');
}

function renderAllChart(balances) {
  const ctx = document.getElementById('allChart').getContext('2d');
  if (allChart) allChart.destroy();
  const datasets = Object.keys(balances).sort().map((name, i) => ({
    label: name,
    data: balances[name].map(d => ({x: new Date(d.t), y: d.bal})),
    borderColor: COLORS[i % COLORS.length],
    backgroundColor: 'transparent',
    borderWidth: 1.5,
    pointRadius: 0,
    tension: 0.3
  }));
  allChart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        x: { type:'time', time:{unit:'hour'}, grid:{color:'#2a2d37'}, ticks:{color:'#9ca3af',font:{size:10}} },
        y: { grid:{color:'#2a2d37'}, ticks:{color:'#9ca3af',font:{size:10}, callback: v=>'R'+v} }
      },
      plugins: {
        legend: { labels:{color:'#e0e0e0',font:{size:11}}, position:'top' },
        tooltip: { callbacks: { label: ctx => ctx.dataset.label+': R'+ctx.parsed.y.toFixed(2) }}
      },
      interaction: { mode:'index', intersect:false }
    }
  });
}

function renderCards(players, balances) {
  const grid = document.getElementById('cards');
  grid.innerHTML = '';
  players.forEach((p, i) => {
    const pnlClass = p.pnl>0?'pos':p.pnl<0?'neg':'flat';
    const pnlSign = p.pnl>=0?'+':'';
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <div class="name"><span class="status-dot dot-active"></span>${p.player}</div>
      <div class="stats">
        <span>R${p.last_bal.toFixed(2)}</span>
        <span>${p.observations} obs</span>
      </div>
      <div class="pnl ${pnlClass}">${pnlSign}R${p.pnl.toFixed(2)}</div>
      <div class="chart-wrap"><canvas id="mini-${p.player}"></canvas></div>
    `;
    grid.appendChild(card);
    const series = balances[p.player] || [];
    if (series.length > 0) {
      setTimeout(() => {
        const ctx = document.getElementById('mini-'+p.player).getContext('2d');
        if (miniCharts[p.player]) miniCharts[p.player].destroy();
        const color = COLORS[i % COLORS.length];
        miniCharts[p.player] = new Chart(ctx, {
          type: 'line',
          data: { datasets: [{
            data: series.map(d=>({x:new Date(d.t),y:d.bal})),
            borderColor: color, backgroundColor: color+'20',
            borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: true
          }]},
          options: {
            responsive:true, maintainAspectRatio:false,
            scales: {
              x:{type:'time',display:false},
              y:{display:false}
            },
            plugins:{legend:{display:false},tooltip:{enabled:false}},
            elements:{point:{radius:0}}
          }
        });
      }, 50);
    }
  });
}

function renderTable(players) {
  const body = document.getElementById('ledgerBody');
  body.innerHTML = '';
  players.forEach(p => {
    const pnlClass = p.pnl>0?'pos':p.pnl<0?'neg':'flat';
    const last = p.last_seen ? new Date(p.last_seen).toLocaleTimeString() : '-';
    body.innerHTML += `<tr>
      <td><span class="status-dot dot-active"></span>${p.player}</td>
      <td>R${p.first_bal.toFixed(2)}</td>
      <td>R${p.last_bal.toFixed(2)}</td>
      <td class="${pnlClass}">${p.pnl>=0?'+':''}R${p.pnl.toFixed(2)}</td>
      <td>R${p.min_bal.toFixed(2)}</td>
      <td>R${p.max_bal.toFixed(2)}</td>
      <td>${p.observations}</td>
      <td>${last}</td>
    </tr>`;
  });
}

load();
setInterval(load, 30000);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8899, debug=False)
