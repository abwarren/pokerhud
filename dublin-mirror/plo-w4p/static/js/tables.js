// Tables list page logic

const TABLES_PAGE = {
  pollTimer: null,

  init() {
    console.log("📊 Initializing tables page");
    this.startPolling();
  },

  destroy() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  },

  startPolling() {
    this.poll();
    this.pollTimer = setInterval(() => this.poll(), 5000);
  },

  async poll() {
    try {
      const data = await API.getTables();
      if (data.ok) {
        STORE.state.tables = data.tables || [];
      }
      this.render();
    } catch (err) {
      console.error("Tables poll error:", err);
      this.render();
    }
  },

  render() {
    const tables = STORE.state.tables || [];
    const statusData = STORE.state.tableStatus || {};

    const statusHtml = `
      <section class="summary-grid">
        <div class="summary-card neutral">
          <div class="summary-title">🗃️📊 Active Tables</div>
          <div class="summary-value">${tables.length}</div>
        </div>
        <div class="summary-card positive">
          <div class="summary-title">👥🎮 Total Players</div>
          <div class="summary-value">${tables.reduce((sum, t) => sum + (t.player_count || 0), 0)}</div>
        </div>
        <div class="summary-card neutral">
          <div class="summary-title">💰💵 Total Pot</div>
          <div class="summary-value">ZAR ${tables.reduce((sum, t) => sum + (t.pot_zar || 0), 0).toFixed(2)}</div>
        </div>
      </section>
    `;

    if (tables.length === 0) {
      setHTML("#page-content", `
        ${statusHtml}
        <div class="empty-state">
          <div class="empty-state-icon">🃏❌</div>
          <div class="empty-state-message">No active tables</div>
          <p style="color: var(--text-muted); margin-top: 8px; font-size: 12px;">
            📡 Inject n4p.js into a poker client to start receiving table data.
          </p>
        </div>
        <div style="margin-top: 12px; text-align: right;">
          <span class="poll-indicator">
            <span class="poll-dot"></span>
            🔄 Polling every 5s
          </span>
        </div>
      `);
      return;
    }

    const tableCards = tables.map(t => {
      const age = t.last_update ? Math.round((Date.now() / 1000) - t.last_update) : 0;
      const ageStr = age < 60 ? `${age}s ago` : `${Math.round(age / 60)}m ago`;

      return `
        <div class="table-list-card" data-action="OPEN_TABLE" data-table="${t.table_id}">
          <div class="table-name">🗃️ ${t.table_id}</div>
          <div class="table-meta">
            <span>${EMOJI.signal(t.variant === "plo" ? "steam" : "")} ${(t.variant || "plo").toUpperCase()}</span>
            <span>👥 ${t.player_count}/9 players</span>
            <span>🃏 ${t.street || "WAITING"}</span>
            <span>💰 ZAR ${(t.pot_zar || 0).toFixed(2)}</span>
            <span>⏰ ${ageStr}</span>
          </div>
        </div>
      `;
    }).join("");

    setHTML("#page-content", `
      ${statusHtml}
      <div class="summary-grid" style="grid-template-columns: 1fr;">
        ${tableCards}
      </div>
      <div style="margin-top: 12px; text-align: right;">
        <span class="poll-indicator">
          <span class="poll-dot"></span>
          🔄 Polling every 5s
        </span>
      </div>
    `);
  }
};
