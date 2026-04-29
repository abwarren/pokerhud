// Bots Manager page module

const BOTS_PAGE = {
  pollTimer: null,
  logModalBot: null,

  init() {
    console.log("🤖 Initializing bots page");
    this.poll();
    this.pollTimer = setInterval(() => this.poll(), 5000);
  },

  destroy() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  },

  async poll() {
    try {
      const data = await API.getBots();
      if (data.ok) {
        STORE.state.bots = data.bots;
        this.render();
      }
    } catch (err) {
      console.error("❌ Bots poll failed:", err);
    }
  },

  render() {
    const bots = STORE.state.bots || [];
    const running = bots.filter(b => b.state === "running").length;
    const stopped = bots.length - running;

    setHTML("#page-content", `
      <section class="summary-grid">
        <div class="summary-card positive">
          <div class="summary-title">🤖🟢 Running</div>
          <div class="summary-value">${running}</div>
        </div>
        <div class="summary-card negative">
          <div class="summary-title">🤖🔴 Stopped</div>
          <div class="summary-value">${stopped}</div>
        </div>
        <div class="summary-card neutral">
          <div class="summary-title">🤖📊 Total Bots</div>
          <div class="summary-value">${bots.length}</div>
        </div>
      </section>

      <!-- Deploy Config -->
      <section class="summary-card" style="margin-bottom: 16px;">
        <div class="summary-title">Deploy Configuration</div>
        <div class="bot-config-grid">
          <div class="bot-config-field">
            <label class="bot-config-label">Players</label>
            <div class="bot-config-input" style="background: var(--bg-secondary); border: none; color: var(--text-muted);" id="player-db-count">Loading from DB...</div>
          </div>
          <div class="bot-config-field">
            <label class="bot-config-label">Table Name</label>
            <input type="text" id="bot-table" class="bot-config-input" value="Belgrade" placeholder="Table name" />
          </div>
          <div class="bot-config-field">
            <label class="bot-config-label">Buy-in Mode</label>
            <select id="bot-buyin" class="bot-config-input">
              <option value="MIN">MIN</option>
              <option value="MAX">MAX</option>
            </select>
          </div>
          <div class="bot-config-field">
            <label class="bot-config-label">Number of Players</label>
            <input type="number" id="bot-count" class="bot-config-input" value="9" min="1" max="20" />
          </div>
        </div>
        <div class="collector-actions" style="margin-top: 12px;">
          <button class="collector-btn parse" data-action="BOTS_DEPLOY">🚀🤖 Deploy Bots</button>
          <button class="collector-btn engine" data-action="BOTS_START_ALL">▶️🤖 Start All</button>
          <button class="collector-btn clear" data-action="BOTS_STOP_ALL">🛑⛔ Stop All</button>
          <button class="collector-btn save" data-action="BOTS_REFRESH">🔄📡 Refresh</button>
        </div>
      </section>

      <!-- EIP Table -->
      <section class="summary-card" style="margin-bottom: 16px;">
        <div class="summary-title">🌐📡 Elastic IP Assignments</div>
        <div class="eip-table">
          <div class="eip-header">
            <span>🏷️ Container</span>
            <span>🌐 Public EIP</span>
            <span>🔒 Private IP</span>
            <span>📡 Status</span>
          </div>
          ${this.renderEipRows(bots)}
        </div>
      </section>

      <!-- Bot Cards Grid -->
      <section>
        <div class="seats-grid">
          ${bots.map(bot => this.renderBotCard(bot)).join("")}
        </div>
      </section>

      <!-- Poll Indicator -->
      <div style="margin-top: 12px; text-align: right;">
        <span class="poll-indicator">
          <span class="poll-dot"></span>
          🔄 Polling every 5s &middot; 🤖 ${bots.length} Bots
        </span>
      </div>

      <!-- Log Modal (hidden by default) -->
      <div id="bot-log-modal" class="log-modal-overlay hidden">
        <div class="log-modal">
          <div class="log-modal-header">
            <span>📜👁️ Bot Logs: <strong id="log-modal-title"></strong></span>
            <button class="action-btn btn-fold" data-action="CLOSE_LOG_MODAL" style="padding: 4px 12px;">✖️ Close</button>
          </div>
          <pre class="log-modal-body" id="log-modal-content">Loading...</pre>
        </div>
      </div>
    `);
  },

  renderEipRows(bots) {
    const players = STORE.state.players || [];
    if (!players.length) {
      this.loadPlayers();
      return '<div class="eip-row"><span class="eip-cell">Loading player EIPs from database...</span></div>';
    }
    return players.map(p => {
      const bot = bots.find(b => b.name === p.container_name);
      const isRunning = bot && bot.state === "running";
      return `
        <div class="eip-row">
          <span class="eip-cell">${p.username}</span>
          <span class="eip-cell eip-value">${p.eip || "—"}</span>
          <span class="eip-cell eip-value">${p.docker_ip || "—"}</span>
          <span class="eip-cell">${isRunning ? "Live" : p.active ? "Ready" : "Inactive"}</span>
        </div>`;
    }).join("");
  },

  async loadPlayers() {
    try {
      const res = await fetch("/api/players");
      if (res.ok) {
        STORE.state.players = await res.json();
        const countEl = document.getElementById("player-db-count");
        if (countEl) countEl.textContent = STORE.state.players.length + " players loaded from DB";
        this.render();
      }
    } catch (err) {
      console.error("Failed to load players:", err);
    }
  },

  renderBotCard(bot) {
    const isRunning = bot.state === "running";
    const env = bot.env || {};

    return `
      <div class="seat-card ${isRunning ? "connected" : "empty-seat"}">
        <div class="seat-header">
          <div>
            <span class="seat-status-dot ${isRunning ? "live" : "offline"}"></span>
            <span class="seat-label">🤖🎰 ${bot.name}</span>
          </div>
          <span class="dealer-chip">${isRunning ? "🟢 UP" : "🔴 DOWN"}</span>
        </div>

        <div class="seat-info">
          <div class="seat-status-text">${isRunning ? "⚡" : "💀"} ${bot.status || "Unknown"}</div>
          <div class="seat-name">👤🎮 ${env.POKER_USERNAME || "Not configured"}</div>
          <div class="seat-stack">🗃️🔢 Table: ${env.TABLE_NUMBER || "N/A"}</div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">💰💵 Buy-in: ${env.BUYIN_AMOUNT || "N/A"}</div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">🌐📡 IP: ${bot.public_ip || "N/A"}</div>
        </div>

        <div class="action-buttons" style="grid-template-columns: repeat(2, 1fr);">
          <button class="action-btn btn-check" data-action="BOT_START" data-bot="${bot.name}" ${isRunning ? "" : ""}>🚀▶️ START</button>
          <button class="action-btn btn-fold" data-action="BOT_STOP" data-bot="${bot.name}">🛑⏹️ STOP</button>
          <button class="action-btn btn-call" data-action="BOT_LOGS" data-bot="${bot.name}">📜👁️ LOGS</button>
          <button class="action-btn btn-raise" data-action="BOT_RESTART" data-bot="${bot.name}">🔄⚡ RESTART</button>
        </div>
      </div>`;
  },

  async deployBots() {
    const tableName = getValue("#bot-table");
    const buyinMode = getValue("#bot-buyin");
    const count = parseInt(getValue("#bot-count")) || 9;

    if (!tableName) {
      alert("Table name is required!");
      return;
    }

    console.log(`Deploying ${count} players...`);
    try {
      const data = await API.deployBots({
        table_name: tableName,
        buy_in_mode: buyinMode,
        bot_count: count,
        mode: "SEATING_ONLY",
        first_action_policy: "CHECK_OR_CALL_ONCE"
      });
      if (data.ok) {
        console.log("Deploy command sent");
        setTimeout(() => this.poll(), 2000);
      }
    } catch (err) {
      console.error("Deploy failed:", err);
      alert("Deploy failed: " + err.message);
    }
  },

  async startBot(name) {
    console.log("▶️ Starting", name);
    try {
      await API.botAction(name, "start");
      setTimeout(() => this.poll(), 2000);
    } catch (err) {
      console.error("❌ Start failed:", err);
      alert("Start failed: " + err.message);
    }
  },

  async stopBot(name) {
    console.log("⏹️ Stopping", name);
    try {
      await API.botAction(name, "stop");
      setTimeout(() => this.poll(), 2000);
    } catch (err) {
      console.error("❌ Stop failed:", err);
      alert("Stop failed: " + err.message);
    }
  },

  async restartBot(name) {
    console.log("🔄 Restarting", name);
    try {
      await API.botAction(name, "restart");
      setTimeout(() => this.poll(), 3000);
    } catch (err) {
      console.error("❌ Restart failed:", err);
      alert("Restart failed: " + err.message);
    }
  },

  async startAll() {
    console.log("🚀 Starting all bots");
    try {
      await API.botsStartAll();
      setTimeout(() => this.poll(), 3000);
    } catch (err) {
      console.error("❌ Start all failed:", err);
      alert("Start all failed: " + err.message);
    }
  },

  async stopAll() {
    console.log("🛑 Stopping all bots");
    try {
      await API.botsStopAll();
      setTimeout(() => this.poll(), 2000);
    } catch (err) {
      console.error("❌ Stop all failed:", err);
      alert("Stop all failed: " + err.message);
    }
  },

  async viewLogs(name) {
    console.log("📜 Viewing logs for", name);
    this.logModalBot = name;

    // Show modal
    const modal = document.getElementById("bot-log-modal");
    if (modal) modal.classList.remove("hidden");
    setHTML("#log-modal-title", name);
    setHTML("#log-modal-content", "⏳ Loading logs...");

    try {
      const data = await API.getBotLogs(name);
      if (data.ok) {
        setHTML("#log-modal-content", data.logs || "(empty)");
      }
    } catch (err) {
      setHTML("#log-modal-content", "❌ Failed to load logs: " + err.message);
    }
  },

  closeLogModal() {
    const modal = document.getElementById("bot-log-modal");
    if (modal) modal.classList.add("hidden");
    this.logModalBot = null;
  }
};
