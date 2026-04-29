// BLM (Basketball Line Monitor) page logic

const BLM_PAGE = {
  pollTimer: null,
  chartInstance: null,
  matches: [],
  selectedMatch: null,
  selectedMarket: "Q2_TOTAL",
  candles: [],
  signal: null,

  async init() {
    console.log("🏀 Initializing BLM page");
    this.loadMockData();
    this.render();
    this.startPolling();
  },

  destroy() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    if (this.chartInstance) {
      this.chartInstance.destroy();
      this.chartInstance = null;
    }
  },

  loadMockData() {
    // Mock matches
    this.matches = [
      {
        id: "nba_lakers_celtics",
        league: "NBA",
        home: "LAL",
        away: "BOS",
        score_home: 54,
        score_away: 48,
        period: "Q2",
        clock: "04:12",
        suspended: false,
        live: true,
      },
      {
        id: "nba_bucks_knicks",
        league: "NBA",
        home: "MIL",
        away: "NYK",
        score_home: 22,
        score_away: 28,
        period: "Q1",
        clock: "02:44",
        suspended: false,
        live: true,
      },
      {
        id: "nba_warriors_nuggets",
        league: "NBA",
        home: "GSW",
        away: "DEN",
        score_home: 0,
        score_away: 0,
        period: "PRE",
        clock: "—",
        suspended: false,
        live: false,
      },
      {
        id: "nba_suns_mavs",
        league: "NBA",
        home: "PHX",
        away: "DAL",
        score_home: 78,
        score_away: 81,
        period: "Q3",
        clock: "08:55",
        suspended: true,
        live: true,
      },
    ];
    this.selectedMatch = this.matches[0]?.id;

    // Generate mock candles
    this.candles = this.generateMockCandles(40);

    // Mock signal
    this.signal = {
      event: "nba_lakers_celtics",
      market: "Q2_TOTAL",
      ts: new Date().toISOString(),
      signal: "LEAN_OVER",
      confidence: 0.74,
      trap_risk: 0.21,
      entry_line_max: 53.5,
      do_not_chase_above: 54.5,
      blm_score: 0.68,
      components: {
        pace: 0.82,
        line_drift: 0.71,
        price_dislocation: 0.58,
        trap: 0.21,
        suspension: 0.12,
        game_state: 0.65,
      },
      quarter_modifier: 1.05,
      reasons: [
        "Pace above baseline (+14%)",
        "Line lagging score by 2.5 pts",
        "No trap freeze detected",
        "Q2 bench rotation noise — slight discount",
      ],
    };
  },

  generateMockCandles(n) {
    const candles = [];
    let price = 1.87;
    let line = 55.5;
    const now = Date.now();
    for (let i = 0; i < n; i++) {
      const o = price;
      const drift = (Math.random() - 0.48) * 0.08;
      const h = o + Math.abs(drift) + Math.random() * 0.04;
      const l = o - Math.abs(drift) - Math.random() * 0.04;
      const c = o + drift;
      price = c;
      const lineDrift = Math.random() > 0.85 ? (Math.random() > 0.5 ? 0.5 : -0.5) : 0;
      line += lineDrift;
      candles.push({
        time: new Date(now - (n - i) * 18000).toLocaleTimeString("en-ZA", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }),
        open: +o.toFixed(3),
        high: +h.toFixed(3),
        low: +l.toFixed(3),
        close: +c.toFixed(3),
        line: line,
        ticks: Math.floor(Math.random() * 12) + 1,
        suspended: Math.random() > 0.92,
        isTrap: Math.random() > 0.88,
      });
    }
    return candles;
  },

  startPolling() {
    this.pollTimer = setInterval(() => {
      this.updateCandles();
    }, 2000);
  },

  updateCandles() {
    const last = this.candles[this.candles.length - 1];
    const drift = (Math.random() - 0.48) * 0.06;
    const o = last.close;
    const c = +(o + drift).toFixed(3);
    const h = +Math.max(o, c, o + Math.random() * 0.03).toFixed(3);
    const l = +Math.min(o, c, o - Math.random() * 0.03).toFixed(3);
    const newCandle = {
      time: new Date().toLocaleTimeString("en-ZA", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
      open: o,
      high: h,
      low: l,
      close: c,
      line: last.line + (Math.random() > 0.9 ? (Math.random() > 0.5 ? 0.5 : -0.5) : 0),
      ticks: Math.floor(Math.random() * 10) + 1,
      suspended: Math.random() > 0.94,
      isTrap: Math.random() > 0.9,
    };
    this.candles.shift();
    this.candles.push(newCandle);
    this.updateChart();
  },

  selectMatch(matchId) {
    this.selectedMatch = matchId;
    this.render();
  },

  selectMarket(market) {
    this.selectedMarket = market;
    this.render();
  },

  render() {
    const match = this.matches.find(m => m.id === this.selectedMatch);
    const markets = ["FG_TOTAL", "Q1_TOTAL", "Q2_TOTAL", "1H_TOTAL", "TT_HOME", "TT_AWAY"];

    const content = `
      <div class="blm-container">
        <!-- Left: Match Grid -->
        <div class="blm-left">
          <div class="blm-panel">
            <div class="blm-panel-header">
              <span class="blm-panel-title">Match Grid</span>
            </div>
            <div class="blm-panel-body">
              ${this.matches.map(m => this.renderMatch(m)).join("")}
            </div>
          </div>

          <div class="blm-panel" style="margin-top: 12px;">
            <div class="blm-panel-header">
              <span class="blm-panel-title">Markets</span>
            </div>
            <div class="blm-panel-body">
              <div class="blm-markets">
                ${markets.map(mk => `
                  <button class="blm-market-btn ${mk === this.selectedMarket ? 'active' : ''}"
                    data-action="BLM_SELECT_MARKET" data-market="${mk}">
                    ${mk}
                  </button>
                `).join("")}
              </div>
            </div>
          </div>
        </div>

        <!-- Center: Chart + Signals -->
        <div class="blm-center">
          ${this.renderChart(match)}
          ${this.renderSignalStack()}
        </div>

        <!-- Right: Bet Assistant -->
        <div class="blm-right">
          ${this.renderBetAssistant()}
          ${this.renderConnection()}
        </div>
      </div>
    `;

    setHTML("#page-content", content);
    this.initChart();
  },

  renderMatch(m) {
    const isSelected = m.id === this.selectedMatch;
    return `
      <div class="blm-match ${isSelected ? 'selected' : ''}"
        data-action="BLM_SELECT_MATCH" data-match="${m.id}">
        <div class="blm-match-header">
          <span class="blm-match-league">${m.league}</span>
          <div class="blm-match-badges">
            ${m.live ? '<span class="blm-badge blm-badge-live">LIVE</span>' : ''}
            ${m.suspended ? '<span class="blm-badge blm-badge-suspended">SUSP</span>' : ''}
          </div>
        </div>
        <div class="blm-match-main">
          <div class="blm-match-teams">
            <span class="blm-match-team">${m.home}</span>
            <span class="blm-match-vs">vs</span>
            <span class="blm-match-team">${m.away}</span>
          </div>
          <div class="blm-match-score">
            <div class="blm-match-score-value">${m.score_home} - ${m.score_away}</div>
            <div class="blm-match-time">${m.period} ${m.clock}</div>
          </div>
        </div>
      </div>
    `;
  },

  renderChart(match) {
    return `
      <div class="blm-panel">
        <div class="blm-panel-header">
          <span class="blm-panel-title">18s Candles — ${match?.home || "—"} vs ${match?.away || "—"} · ${this.selectedMarket}</span>
          <div class="blm-chart-legend">
            <span class="blm-legend-item"><span class="blm-legend-trap"></span>Trap</span>
            <span class="blm-legend-item"><span class="blm-legend-freeze"></span>Freeze</span>
          </div>
        </div>
        <div class="blm-panel-body">
          <canvas id="blm-chart" width="800" height="280"></canvas>
        </div>
      </div>
    `;
  },

  renderSignalStack() {
    return `
      <div class="blm-panel" style="margin-top: 16px;">
        <div class="blm-panel-header">
          <span class="blm-panel-title">BLM Signal Stack</span>
        </div>
        <div class="blm-panel-body">
          <div class="blm-signal-grid">
            <div>
              ${this.renderSignalBar("Pace", this.signal.components.pace, "#22d3ee")}
              ${this.renderSignalBar("Line Drift", this.signal.components.line_drift, "#f59e0b")}
            </div>
            <div>
              ${this.renderSignalBar("Price Dislocation", this.signal.components.price_dislocation, "#10b981")}
              ${this.renderSignalBar("Trap", this.signal.components.trap, "#a855f7")}
            </div>
            <div>
              ${this.renderSignalBar("Suspension", this.signal.components.suspension, "#3b82f6")}
              ${this.renderSignalBar("Game State", this.signal.components.game_state, "#64748b")}
            </div>
          </div>
          <div class="blm-signal-summary">
            <div class="blm-score-box">
              <span class="blm-score-label">BLM SCORE</span>
              <div class="blm-score-value">${(this.signal.blm_score * 100).toFixed(0)}</div>
            </div>
            <div class="blm-score-box">
              <span class="blm-score-label">QTR MOD</span>
              <div class="blm-score-mod">×${this.signal.quarter_modifier.toFixed(2)}</div>
            </div>
            <div class="blm-score-box">
              <span class="blm-score-label">CONFIDENCE</span>
              <div class="blm-score-conf" style="color: ${this.confidenceColor(this.signal.confidence)}">
                ${(this.signal.confidence * 100).toFixed(0)}%
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  },

  renderSignalBar(label, value, color) {
    const pct = Math.min(value * 100, 100);
    return `
      <div class="blm-signal-bar">
        <div class="blm-signal-bar-header">
          <span class="blm-signal-bar-label">${label}</span>
          <span class="blm-signal-bar-value">${(value * 100).toFixed(0)}%</span>
        </div>
        <div class="blm-signal-bar-track">
          <div class="blm-signal-bar-fill" style="width: ${pct}%; background: ${color};"></div>
        </div>
      </div>
    `;
  },

  renderBetAssistant() {
    const signalColor = this.getSignalColor(this.signal.signal);
    return `
      <div class="blm-panel">
        <div class="blm-panel-header">
          <span class="blm-panel-title">Manual Bet Assistant</span>
        </div>
        <div class="blm-panel-body">
          <div class="blm-assistant-signal">
            <span class="blm-badge" style="background: ${signalColor}; color: #000;">
              ${this.signal.signal.replace(/_/g, " ")}
            </span>
            <div class="blm-assistant-market">${this.signal.market}</div>
          </div>

          <div class="blm-assistant-levels">
            <div class="blm-assistant-row">
              <span class="blm-assistant-label">ENTRY ≤</span>
              <span class="blm-assistant-value" style="color: #10b981;">${this.signal.entry_line_max}</span>
            </div>
            <div class="blm-assistant-row">
              <span class="blm-assistant-label">NO CHASE ></span>
              <span class="blm-assistant-value" style="color: #ef4444;">${this.signal.do_not_chase_above}</span>
            </div>
          </div>

          <div class="blm-trap-risk">
            <div class="blm-trap-risk-header">
              <span class="blm-trap-risk-label">TRAP RISK</span>
              <span class="blm-trap-risk-value">${(this.signal.trap_risk * 100).toFixed(0)}%</span>
            </div>
            <div class="blm-trap-risk-track">
              <div class="blm-trap-risk-fill" style="width: ${this.signal.trap_risk * 100}%; background: ${this.getTrapColor(this.signal.trap_risk)};"></div>
            </div>
          </div>

          <div class="blm-reasoning">
            <span class="blm-reasoning-title">REASONING</span>
            ${this.signal.reasons.map(r => `
              <div class="blm-reasoning-item">
                <span class="blm-reasoning-bullet">›</span>
                ${r}
              </div>
            `).join("")}
          </div>
        </div>
      </div>
    `;
  },

  renderConnection() {
    return `
      <div class="blm-panel" style="margin-top: 12px;">
        <div class="blm-panel-header">
          <span class="blm-panel-title">Connection</span>
        </div>
        <div class="blm-panel-body">
          <div class="blm-connection">
            <div class="blm-connection-row">
              <span class="blm-connection-label">Endpoint:</span>
              <span class="blm-connection-value">mock://local</span>
            </div>
            <div class="blm-connection-row">
              <span class="blm-connection-label">Poll:</span>
              <span class="blm-connection-value">2000ms</span>
            </div>
            <div class="blm-connection-row">
              <span class="blm-connection-label">Candle Interval:</span>
              <span class="blm-connection-value" style="color: #22d3ee;">18s</span>
            </div>
          </div>
        </div>
      </div>
    `;
  },

  initChart() {
    const canvas = document.getElementById("blm-chart");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    this.renderCandlestickChart(ctx, canvas);
  },

  renderCandlestickChart(ctx, canvas) {
    const width = canvas.width;
    const height = canvas.height;
    const padding = { top: 20, right: 60, bottom: 40, left: 60 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#111827";
    ctx.fillRect(0, 0, width, height);

    // Find price range
    const prices = this.candles.flatMap(c => [c.low, c.high]);
    const lines = this.candles.map(c => c.line);
    const minPrice = Math.min(...prices) - 0.05;
    const maxPrice = Math.max(...prices) + 0.05;
    const minLine = Math.min(...lines) - 1;
    const maxLine = Math.max(...lines) + 1;

    const scaleY = (val) => padding.top + chartHeight - ((val - minPrice) / (maxPrice - minPrice)) * chartHeight;
    const scaleLineY = (val) => padding.top + chartHeight - ((val - minLine) / (maxLine - minLine)) * chartHeight;
    const candleWidth = chartWidth / this.candles.length;

    // Draw grid
    ctx.strokeStyle = "#334155";
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 5; i++) {
      const y = padding.top + (chartHeight / 5) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();
    }

    // Draw candles
    this.candles.forEach((candle, i) => {
      const x = padding.left + i * candleWidth;
      const isUp = candle.close >= candle.open;
      const color = isUp ? "#10b981" : "#ef4444";

      // Wick
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x + candleWidth / 2, scaleY(candle.high));
      ctx.lineTo(x + candleWidth / 2, scaleY(candle.low));
      ctx.stroke();

      // Body
      const bodyTop = scaleY(Math.max(candle.open, candle.close));
      const bodyBottom = scaleY(Math.min(candle.open, candle.close));
      const bodyHeight = Math.max(bodyBottom - bodyTop, 1);
      ctx.fillStyle = color;
      ctx.fillRect(x + candleWidth * 0.2, bodyTop, candleWidth * 0.6, bodyHeight);

      // Trap marker
      if (candle.isTrap) {
        ctx.fillStyle = "#a855f7";
        ctx.beginPath();
        ctx.moveTo(x + candleWidth / 2, scaleY(candle.high) - 10);
        ctx.lineTo(x + candleWidth / 2 - 4, scaleY(candle.high) - 4);
        ctx.lineTo(x + candleWidth / 2 + 4, scaleY(candle.high) - 4);
        ctx.fill();
      }

      // Freeze marker
      if (candle.suspended) {
        ctx.fillStyle = "#3b82f6";
        ctx.beginPath();
        ctx.arc(x + candleWidth / 2, scaleY(candle.low) + 8, 3, 0, 2 * Math.PI);
        ctx.fill();
      }
    });

    // Draw line overlay
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 2]);
    ctx.beginPath();
    this.candles.forEach((candle, i) => {
      const x = padding.left + i * candleWidth + candleWidth / 2;
      const y = scaleLineY(candle.line);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw Y-axis labels (price)
    ctx.fillStyle = "#64748b";
    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.textAlign = "right";
    for (let i = 0; i <= 5; i++) {
      const val = minPrice + (maxPrice - minPrice) * (i / 5);
      const y = padding.top + chartHeight - (chartHeight / 5) * i;
      ctx.fillText(val.toFixed(3), padding.left - 10, y + 4);
    }

    // Draw Y-axis labels (line) - right side
    ctx.textAlign = "left";
    ctx.fillStyle = "#f59e0b";
    for (let i = 0; i <= 5; i++) {
      const val = minLine + (maxLine - minLine) * (i / 5);
      const y = padding.top + chartHeight - (chartHeight / 5) * i;
      ctx.fillText(val.toFixed(1), width - padding.right + 10, y + 4);
    }

    // Draw X-axis labels (time)
    ctx.fillStyle = "#64748b";
    ctx.textAlign = "center";
    const step = Math.floor(this.candles.length / 8);
    this.candles.forEach((candle, i) => {
      if (i % step === 0) {
        const x = padding.left + i * candleWidth + candleWidth / 2;
        ctx.fillText(candle.time, x, height - 10);
      }
    });
  },

  updateChart() {
    const canvas = document.getElementById("blm-chart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    this.renderCandlestickChart(ctx, canvas);
  },

  getSignalColor(signal) {
    const map = {
      LEAN_OVER: "#10b981",
      LEAN_UNDER: "#ef4444",
      WATCH: "#f59e0b",
      NO_BET: "#64748b",
      HIGH_TRAP_RISK: "#a855f7",
      STRONG_LEAN_OVER: "#10b981",
      STRONG_LEAN_UNDER: "#ef4444",
    };
    return map[signal] || "#64748b";
  },

  confidenceColor(conf) {
    if (conf >= 0.7) return "#10b981";
    if (conf >= 0.5) return "#f59e0b";
    return "#ef4444";
  },

  getTrapColor(risk) {
    if (risk > 0.6) return "#a855f7";
    if (risk > 0.3) return "#f59e0b";
    return "#10b981";
  },
};
