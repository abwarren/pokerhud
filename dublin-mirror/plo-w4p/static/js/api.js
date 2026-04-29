// API client

const API = {
  async getSession() {
    const res = await fetch("/api/session");
    if (!res.ok) {
      throw new Error(`Session API error: ${res.status}`);
    }
    return await res.json();
  },

  async getLogs(filters = {}) {
    const qs = new URLSearchParams(filters).toString();
    const res = await fetch(`/api/logs?${qs}`);
    if (!res.ok) {
      throw new Error(`Logs API error: ${res.status}`);
    }
    return await res.json();
  },

  async getLedger(filters = {}) {
    const qs = new URLSearchParams(filters).toString();
    const res = await fetch(`/api/ledger?${qs}`);
    if (!res.ok) {
      throw new Error(`Ledger API error: ${res.status}`);
    }
    return await res.json();
  },

  // Remote Control APIs (proxied to avoid CORS)
  async getTableLatest() {
    const res = await fetch("/api/remote/table/latest");
    if (!res.ok) {
      throw new Error(`Table API error: ${res.status}`);
    }
    return await res.json();
  },

  async getTables() {
    const res = await fetch("/api/tables");
    if (!res.ok) {
      throw new Error(`Tables API error: ${res.status}`);
    }
    return await res.json();
  },

  async getTable(tableId) {
    const res = await fetch(`/api/table/${tableId}`);
    if (!res.ok) {
      throw new Error(`Table API error: ${res.status}`);
    }
    return await res.json();
  },

  async queueCommand(tableId, seatIndex, commandType) {
    const res = await fetch("/api/remote/commands/queue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        table_id: tableId,
        seat_index: seatIndex,
        command_type: commandType
      })
    });
    if (!res.ok) {
      throw new Error(`Command API error: ${res.status}`);
    }
    return await res.json();
  },

  async getHealth() {
    const res = await fetch("/health");
    if (!res.ok) {
      throw new Error(`Health API error: ${res.status}`);
    }
    return await res.json();
  },

  // Collector APIs
  async getCollectorLatest() {
    const res = await fetch("/api/collector/latest");
    if (!res.ok) {
      throw new Error(`Collector API error: ${res.status}`);
    }
    return await res.json();
  },

  async saveCollectorHands(hands) {
    const res = await fetch("/collector/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hands })
    });
    if (!res.ok) {
      throw new Error(`Collector save error: ${res.status}`);
    }
    return await res.json();
  },

  async getCollectorMeta() {
    const res = await fetch("/collector/meta");
    if (!res.ok) {
      throw new Error(`Collector meta error: ${res.status}`);
    }
    return await res.json();
  },

  // Engine APIs
  async calculateEquity(variant, heroHand, board) {
    const res = await fetch("/api/equity/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        variant: variant,
        hero_hand: heroHand,
        board: board,
        villain_hands: []
      })
    });
    if (!res.ok) {
      throw new Error(`Equity API error: ${res.status}`);
    }
    return await res.json();
  },

  // Bots APIs
  async getBots() {
    const res = await fetch("/api/bots");
    if (!res.ok) throw new Error(`Bots API error: ${res.status}`);
    return await res.json();
  },

  async botAction(name, action) {
    const res = await fetch(`/api/bots/${name}/${action}`, { method: "POST" });
    if (!res.ok) throw new Error(`Bot action error: ${res.status}`);
    return await res.json();
  },

  async getBotLogs(name, lines = 100) {
    const res = await fetch(`/api/bots/${name}/logs?lines=${lines}`);
    if (!res.ok) throw new Error(`Bot logs error: ${res.status}`);
    return await res.json();
  },

  async botsStartAll() {
    const res = await fetch("/api/bots/start-all", { method: "POST" });
    if (!res.ok) throw new Error(`Start all error: ${res.status}`);
    return await res.json();
  },

  async botsStopAll() {
    const res = await fetch("/api/bots/stop-all", { method: "POST" });
    if (!res.ok) throw new Error(`Stop all error: ${res.status}`);
    return await res.json();
  },

  async deployBots(config) {
    const res = await fetch("/api/bots/deploy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    });
    if (!res.ok) throw new Error(`Deploy error: ${res.status}`);
    return await res.json();
  }
};
