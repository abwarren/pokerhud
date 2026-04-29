// Ledger page logic

const LEDGER_PAGE = {
  async init() {
    console.log("💰 Initializing ledger page");
    await CONTROLLER.loadLedger();
  },

  destroy() {},

  readFilters() {
    return {
      type: getValue("#filter-type"),
      q: getValue("#filter-q")
    };
  },

  renderTable() {
    const rows = STORE.state.ledger.rows;

    const summary = this.calculateSummary(rows);
    const balanceClass = summary.balance >= 0 ? "positive" : "negative";

    const content = `
      <section class="summary-grid">
        <div class="summary-card ${balanceClass}">
          <div class="summary-title">💰💵 Current Balance</div>
          <div class="summary-value">R ${summary.balance.toFixed(2)}</div>
        </div>
        <div class="summary-card positive">
          <div class="summary-title">📈💚 Total Credits</div>
          <div class="summary-value">R ${summary.credits.toFixed(2)}</div>
        </div>
        <div class="summary-card negative">
          <div class="summary-title">📉💔 Total Debits</div>
          <div class="summary-value">R ${summary.debits.toFixed(2)}</div>
        </div>
      </section>

      <section>
        <form id="ledger-filter-form" class="filter-bar">
          <select id="filter-type">
            <option value="">💸 All Types</option>
            <option value="credit">📈 Credit</option>
            <option value="debit">📉 Debit</option>
            <option value="adjustment">⚙️ Adjustment</option>
          </select>
          <input id="filter-q" type="text" placeholder="🔍 Search ledger entries..." />
          <button type="submit">🔍✨ Filter</button>
          <button type="button" data-action="REFRESH_LEDGER">🔄⚡ Refresh</button>
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
            <th>📅 Date</th>
            <th>🔖 Reference</th>
            <th>💸 Type</th>
            <th>💰 Amount</th>
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
    const amountClass = row.type === "credit" ? "positive" : row.type === "debit" ? "negative" : "neutral";
    const typeEmoji = row.type === "credit" ? "📈" : row.type === "debit" ? "📉" : "⚙️";
    return `
      <tr>
        <td>${row.date || "-"}</td>
        <td>${row.reference || "-"}</td>
        <td>${typeEmoji} ${row.type || "-"}</td>
        <td class="${amountClass}">R ${parseFloat(row.amount || 0).toFixed(2)}</td>
        <td>${EMOJI.status(row.status)} ${row.status || "-"}</td>
      </tr>
    `;
  },

  emptyState() {
    return `
      <div class="empty-state">
        <div class="empty-state-icon">💰❌</div>
        <div class="empty-state-message">No ledger entries found</div>
      </div>
    `;
  },

  calculateSummary(rows) {
    let credits = 0;
    let debits = 0;

    rows.forEach(row => {
      const amount = parseFloat(row.amount || 0);
      if (row.type === "credit") {
        credits += amount;
      } else if (row.type === "debit") {
        debits += amount;
      }
    });

    return {
      credits,
      debits,
      balance: credits - debits
    };
  }
};
