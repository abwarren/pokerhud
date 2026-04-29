// Global event controller

const CONTROLLER = {
  initGlobalListeners() {
    console.log("🎮 Initializing global event listeners");

    document.addEventListener("click", this.handleClick.bind(this));
    document.addEventListener("submit", this.handleSubmit.bind(this));
    document.addEventListener("change", this.handleChange.bind(this));
  },

  handleClick(event) {
    // Handle inject copy button (no data-action, matched by ID)
    if (event.target.id === "copy-inject-btn") {
      REMOTE_PAGE.copyInjectCode();
      return;
    }

    const el = event.target.closest("[data-action]");
    if (!el) return;

    const action = el.dataset.action;

    switch (action) {
      case "NAVIGATE":
        window.location.href = el.dataset.target;
        break;

      case "REFRESH_LOGS":
        this.loadLogs();
        break;

      case "REFRESH_LEDGER":
        this.loadLedger();
        break;

      case "SEAT_CMD":
        REMOTE_PAGE.sendCommand(el.dataset.table, parseInt(el.dataset.seat), el.dataset.cmd);
        break;

      case "COPY_INJECT":
        REMOTE_PAGE.copyInjectCode();
        break;

      case "OPEN_TABLE":
        window.location.href = "/remote";
        break;

      // Collector actions
      case "PARSE_HANDS":
        COLLECTOR_PAGE.parseHands();
        break;

      case "CLEAR_COLLECTOR":
        COLLECTOR_PAGE.clearCollector();
        break;

      case "SAVE_HANDS":
        COLLECTOR_PAGE.saveHands();
        break;

      case "SEND_TO_ENGINE":
        COLLECTOR_PAGE.sendToEngine();
        break;

      case "SELECT_HAND":
        COLLECTOR_PAGE.selectHand(parseInt(el.dataset.index));
        break;

      // Engine actions
      case "ENGINE_PARSE":
        ENGINE_PAGE.parseImport();
        break;

      case "ENGINE_PARSE_RUN":
        ENGINE_PAGE.parseAndRun();
        break;

      case "ENGINE_SELECT_HAND":
        ENGINE_PAGE.selectHand(parseInt(el.dataset.index));
        break;

      case "RUN_ENGINE":
        ENGINE_PAGE.runEngine();
        break;

      case "CLEAR_ENGINE":
        ENGINE_PAGE.clearEngine();
        break;

      case "CLEAR_INPUT":
        ENGINE_PAGE.clearInput();
        break;

      // Bot actions
      case "BOT_START":
        BOTS_PAGE.startBot(el.dataset.bot);
        break;
      case "BOT_STOP":
        BOTS_PAGE.stopBot(el.dataset.bot);
        break;
      case "BOT_RESTART":
        BOTS_PAGE.restartBot(el.dataset.bot);
        break;
      case "BOT_LOGS":
        BOTS_PAGE.viewLogs(el.dataset.bot);
        break;
      case "BOTS_START_ALL":
        BOTS_PAGE.startAll();
        break;
      case "BOTS_STOP_ALL":
        BOTS_PAGE.stopAll();
        break;
      case "BOTS_REFRESH":
        BOTS_PAGE.poll();
        break;
      case "BOTS_DEPLOY":
        BOTS_PAGE.deployBots();
        break;
      case "CLOSE_LOG_MODAL":
        BOTS_PAGE.closeLogModal();
        break;

      // BLM actions
      case "BLM_SELECT_MATCH":
        BLM_PAGE.selectMatch(el.dataset.match);
        break;
      case "BLM_SELECT_MARKET":
        BLM_PAGE.selectMarket(el.dataset.market);
        break;

      default:
        console.warn("⚠️  Unknown action:", action);
    }
  },

  handleChange(event) {
    const el = event.target;
    if (el.dataset.action === "PRE_ACTION") {
      REMOTE_PAGE.togglePreAction(
        el.dataset.table,
        parseInt(el.dataset.seat),
        el.dataset.preaction,
        el.checked
      );
    }
    if (el.dataset.action === "ENGINE_VARIANT_CHANGE") {
      ENGINE_PAGE.updateEngineInfo();
    }
  },

  handleSubmit(event) {
    const form = event.target;

    if (form.matches("#logs-filter-form")) {
      event.preventDefault();
      this.loadLogs();
    } else if (form.matches("#ledger-filter-form")) {
      event.preventDefault();
      this.loadLedger();
    }
  },

  async loadLogs() {
    console.log("📋 Loading logs");

    try {
      const filters = LOGS_PAGE.readFilters();
      const rows = await API.getLogs(filters);
      STORE.state.logs.rows = rows;
      LOGS_PAGE.renderTable();
      console.log("✅ Logs loaded:", rows.length, "rows");
    } catch (error) {
      console.error("❌ Failed to load logs:", error);
      alert("Failed to load logs");
    }
  },

  async loadLedger() {
    console.log("💰 Loading ledger");

    try {
      const filters = LEDGER_PAGE.readFilters();
      const rows = await API.getLedger(filters);
      STORE.state.ledger.rows = rows;
      LEDGER_PAGE.renderTable();
      console.log("✅ Ledger loaded:", rows.length, "rows");
    } catch (error) {
      console.error("❌ Failed to load ledger:", error);
      alert("Failed to load ledger");
    }
  }
};
