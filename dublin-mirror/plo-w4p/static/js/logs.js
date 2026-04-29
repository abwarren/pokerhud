// Logs page logic

const LOGS_PAGE = {
  async init() {
    console.log("📋 Initializing logs page");
    await CONTROLLER.loadLogs();
  },

  destroy() {},

  readFilters() {
    return {
      level: getValue("#filter-level"),
      q: getValue("#filter-q")
    };
  },

  renderTable() {
    const rows = STORE.state.logs.rows;

    const content = `
      <section>
        <form id="logs-filter-form" class="filter-bar">
          <select id="filter-level">
            <option value="">📊 All Levels</option>
            <option value="info">📘 Info</option>
            <option value="warn">⚠️ Warn</option>
            <option value="error">❌ Error</option>
          </select>
          <input id="filter-q" type="text" placeholder="🔍 Search activity logs..." />
          <button type="submit">🔍✨ Filter</button>
          <button type="button" data-action="REFRESH_LOGS">🔄⚡ Refresh</button>
        </form>

        ${rows.length === 0 ? this.emptyState() : this.tableHtml(rows)}
      </section>
    `;

    setHTML("#page-content", content);
  },

  tableHtml(rows) {
    return `
      <table class="data-table">
        <thead>
          <tr>
            <th>⏰ Time</th>
            <th>📊 Level</th>
            <th>👤 Actor</th>
            <th>🎯 Event</th>
            <th>✅ Status</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(this.rowHtml).join("")}
        </tbody>
      </table>
    `;
  },

  rowHtml(row) {
    return `
      <tr>
        <td>${row.timestamp || "-"}</td>
        <td>${EMOJI.level(row.level)} ${row.level || "-"}</td>
        <td>${row.actor || "-"}</td>
        <td>${row.event || "-"}</td>
        <td>${EMOJI.status(row.status)} ${row.status || "-"}</td>
      </tr>
    `;
  },

  emptyState() {
    return `
      <div class="empty-state">
        <div class="empty-state-icon">📋❌</div>
        <div class="empty-state-message">No activity logs found</div>
      </div>
    `;
  }
};
