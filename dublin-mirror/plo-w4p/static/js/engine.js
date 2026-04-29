// Equity Engine page logic

const ENGINE_PAGE = {
  selectedHandIndex: null,
  parsedHands: [],
  calculating: false,

  // Game constraints
  VARIANT_CONFIG: {
    "PLO4-6MAX": { players: 6, hole_cards: 4 },
    "PLO4-8MAX": { players: 8, hole_cards: 4 },
    "PLO4-9MAX": { players: 9, hole_cards: 4 },
    "PLO5-6MAX": { players: 6, hole_cards: 5 },
    "PLO5-5MAX": { players: 5, hole_cards: 5 },
    "PLO6-5MAX": { players: 5, hole_cards: 6 },
    "PLO6-6MAX": { players: 6, hole_cards: 6 }
  },

  init() {
    console.log("🧮 Initializing equity engine page");
    this.render();
    this.checkIncomingHand();
    this.loadFromCollector();
  },

  destroy() {},

  checkIncomingHand() {
    // Check if collector sent a hand via STORE
    if (STORE.state.engineInput) {
      const input = STORE.state.engineInput;
      this.parsedHands = [{
        hero: input.hero,
        board: input.board,
        variant: input.variant,
        raw: input.raw,
        selected: true
      }];
      this.selectedHandIndex = 0;

      // Auto-select variant
      setTimeout(() => {
        const select = document.getElementById("variant-select");
        if (select && input.variant) {
          const fullVariant = this.detectFullVariant(input.variant, input.hero);
          if (fullVariant) select.value = fullVariant;
        }
        this.updateEngineInfo();
        this.render();
      }, 100);

      STORE.state.engineInput = null;
    }
  },

  async loadFromCollector() {
    if (this.parsedHands.length > 0) return;
    try {
      const data = await API.getCollectorLatest();
      if (data.ok && data.raw) {
        const el = document.getElementById("engine-import-textarea");
        if (el) el.value = data.raw;
      }
    } catch (err) {
      // No collector data — that's fine
    }
  },

  detectFullVariant(shortVariant, heroHand) {
    if (!shortVariant) return null;
    // Default to 6MAX
    const defaults = { "PLO4": "PLO4-6MAX", "PLO5": "PLO5-6MAX", "PLO6": "PLO6-6MAX" };
    return defaults[shortVariant] || null;
  },

  render() {
    const selectedHand = this.selectedHandIndex !== null ? this.parsedHands[this.selectedHandIndex] : null;

    setHTML("#page-content", `
      <section class="summary-grid">
        <div class="summary-card neutral">
          <div class="summary-title">🧮🔢 Engine Status</div>
          <div class="summary-value">${this.calculating ? "Calculating..." : "Ready"}</div>
        </div>
        <div class="summary-card neutral">
          <div class="summary-title">🂠✋ Selected Hand</div>
          <div class="summary-value">${selectedHand ? selectedHand.hero : "None"}</div>
        </div>
        <div class="summary-card neutral">
          <div class="summary-title">🎰📊 Variant</div>
          <div class="summary-value">${selectedHand ? (selectedHand.variant || "Auto") : "—"}</div>
        </div>
      </section>

      <div class="engine-layout">
        <!-- Left: Import Panel -->
        <div class="engine-panel-left">
          <section class="summary-card">
            <div class="summary-title">📥✏️ Import Hands</div>
            <textarea id="engine-import-textarea" class="collector-textarea" style="min-height: 120px;"
              placeholder="Paste hand data here...&#10;&#10;Example: AsKdQcJh&#10;Board: 9sTd2c"></textarea>
            <div class="collector-actions" style="margin-top: 8px;">
              <button data-action="ENGINE_PARSE_RUN" class="collector-btn parse">🚀 Parse & Run</button>
              <button data-action="CLEAR_INPUT" class="collector-btn clear">🗑️ Clear Input</button>
            </div>
          </section>

          <section class="summary-card" style="margin-top: 12px;">
            <div class="summary-title">🂠📋 Hand List (${this.parsedHands.length})</div>
            <div class="hand-list-container">
              ${this.parsedHands.length > 0 ? this.renderHandList() : '<div style="color: var(--text-faint); font-size: 11px; padding: 12px;">📭 No hands loaded</div>'}
            </div>
          </section>
        </div>

        <!-- Right: Engine Panel -->
        <div class="engine-panel-right">
          <section class="summary-card">
            <div class="summary-title">🎰⚙️ Game Variant</div>
            <select id="variant-select" class="engine-variant-select" data-action="ENGINE_VARIANT_CHANGE">
              <option value="">— Select Variant —</option>
              <option value="PLO4-6MAX">🃏 PLO4-6MAX (6 players, 4 hole cards)</option>
              <option value="PLO4-8MAX">🃏 PLO4-8MAX (8 players, 4 hole cards)</option>
              <option value="PLO4-9MAX">🃏 PLO4-9MAX (9 players, 4 hole cards)</option>
              <option value="PLO5-6MAX">🃏 PLO5-6MAX (6 players, 5 hole cards)</option>
              <option value="PLO5-5MAX">🃏 PLO5-5MAX (5 players, 5 hole cards)</option>
              <option value="PLO6-5MAX">🃏 PLO6-5MAX (5 players, 6 hole cards)</option>
              <option value="PLO6-6MAX">🃏 PLO6-6MAX (6 players, 6 hole cards)</option>
            </select>
          </section>

          <section class="summary-card" style="margin-top: 12px;">
            <div class="summary-title">📊🔍 Engine Input</div>
            <div class="engine-info-grid">
              <div class="engine-info-row">
                <span class="engine-info-label">🎰 Variant:</span>
                <span id="info-variant" class="engine-info-value">${selectedHand ? (selectedHand.variant || "Not selected") : "Not selected"}</span>
              </div>
              <div class="engine-info-row">
                <span class="engine-info-label">🂠 Hero Hand:</span>
                <span id="info-hero" class="engine-info-value">${selectedHand ? selectedHand.hero : "Not selected"}</span>
              </div>
              <div class="engine-info-row">
                <span class="engine-info-label">🃏 Board:</span>
                <span id="info-board" class="engine-info-value">${selectedHand ? (selectedHand.board || "none") : "Not selected"}</span>
              </div>
              <div class="engine-info-row">
                <span class="engine-info-label">⚙️ Config:</span>
                <span id="info-config" class="engine-info-value">—</span>
              </div>
            </div>
          </section>

          <section class="summary-card" style="margin-top: 12px;">
            <div class="summary-title">📈💹 Results</div>
            <textarea id="engine-results" class="engine-results-textarea" readonly
              placeholder="🧮 Select a hand and variant, then click Calculate Equity..."></textarea>
            <div class="collector-actions" style="margin-top: 8px;">
              <button data-action="RUN_ENGINE" class="collector-btn save" ${!selectedHand ? "disabled" : ""}>🧮🔥 Calculate Equity</button>
              <button data-action="CLEAR_ENGINE" class="collector-btn clear">🗑️ Clear</button>
            </div>
          </section>
        </div>
      </div>
    `);
  },

  renderHandList() {
    return this.parsedHands.map((hand, idx) => {
      const isSelected = this.selectedHandIndex === idx;
      const variantBadge = hand.variant ? `<span class="hand-variant-badge">🎰 ${hand.variant}</span>` : "";

      return `
        <div class="hand-list-item ${isSelected ? 'selected' : ''}" data-action="ENGINE_SELECT_HAND" data-index="${idx}">
          <div class="hand-hero">🂠 ${hand.hero || "Unknown"}</div>
          <div class="hand-board">🃏 ${hand.board || "no board"}</div>
          ${variantBadge}
        </div>
      `;
    }).join("");
  },

  parseImport() {
    const textarea = document.getElementById("engine-import-textarea");
    if (!textarea || !textarea.value.trim()) {
      alert("📋 Please paste hand data first");
      return;
    }

    const text = textarea.value.trim();
    this.parsedHands = [];
    this.selectedHandIndex = null;

    const lines = text.split("\n").map(l => l.trim()).filter(l => l);
    let i = 0;

    while (i < lines.length) {
      const clean = lines[i].replace(/\s/g, "");
      // Check if valid hero hand (8-14 chars of card notation)
      if (clean.length >= 8 && clean.length <= 14 && /^[AKQJT2-9][shdc]/i.test(clean)) {
        const hero = clean;
        const board = (i + 1 < lines.length) ? lines[i + 1].replace(/\s/g, "") : "";
        const holeCards = hero.length / 2;
        let variant = null;
        if (holeCards === 4) variant = "PLO4";
        else if (holeCards === 5) variant = "PLO5";
        else if (holeCards === 6) variant = "PLO6";

        this.parsedHands.push({ hero, board, variant, selected: false });
        i += 2;
      } else {
        i++;
      }
    }

    console.log(`🧮 Parsed ${this.parsedHands.length} hands for engine`);
    this.render();
  },

  async parseAndRun() {
    // Step 1: Parse
    const textarea = document.getElementById("engine-import-textarea");
    if (!textarea || !textarea.value.trim()) {
      alert("📋 Please paste hand data first");
      return;
    }

    const text = textarea.value.trim();
    this.parsedHands = [];
    this.selectedHandIndex = null;

    const lines = text.split("\n").map(l => l.trim()).filter(l => l);
    let i = 0;

    while (i < lines.length) {
      const clean = lines[i].replace(/\s/g, "");
      if (clean.length >= 8 && clean.length <= 14 && /^[AKQJT2-9][shdc]/i.test(clean)) {
        const hero = clean;
        const board = (i + 1 < lines.length) ? lines[i + 1].replace(/\s/g, "") : "";
        const holeCards = hero.length / 2;
        let variant = null;
        if (holeCards === 4) variant = "PLO4";
        else if (holeCards === 5) variant = "PLO5";
        else if (holeCards === 6) variant = "PLO6";

        this.parsedHands.push({ hero, board, variant, selected: false });
        i += 2;
      } else {
        i++;
      }
    }

    if (this.parsedHands.length === 0) {
      alert("❌ No valid hands found to parse");
      return;
    }

    console.log(`🧮 Parsed ${this.parsedHands.length} hands for engine`);

    // Step 2: Auto-select first hand
    this.selectedHandIndex = 0;
    this.parsedHands[0].selected = true;
    const hand = this.parsedHands[0];

    // Step 3: Auto-detect and set variant
    const fullVariant = this.detectFullVariant(hand.variant, hand.hero);
    if (!fullVariant) {
      alert("❌ Could not detect game variant");
      this.render();
      return;
    }

    // Step 4: Render and update info
    this.render();

    // Wait for DOM update
    await new Promise(resolve => setTimeout(resolve, 100));

    const variantSelect = document.getElementById("variant-select");
    if (variantSelect) variantSelect.value = fullVariant;
    this.updateEngineInfo();

    // Step 5: Run engine automatically
    await this.runEngine();
  },

  selectHand(index) {
    this.selectedHandIndex = index;
    this.parsedHands.forEach((h, i) => { h.selected = (i === index); });

    // Auto-select variant if possible
    const hand = this.parsedHands[index];
    if (hand && hand.variant) {
      const fullVariant = this.detectFullVariant(hand.variant, hand.hero);
      const select = document.getElementById("variant-select");
      if (select && fullVariant) select.value = fullVariant;
    }

    this.updateEngineInfo();
    this.render();
  },

  updateEngineInfo() {
    if (this.selectedHandIndex === null) return;
    const hand = this.parsedHands[this.selectedHandIndex];
    const variantSelect = document.getElementById("variant-select");
    const variant = variantSelect ? variantSelect.value : "";

    const infoVariant = document.getElementById("info-variant");
    const infoHero = document.getElementById("info-hero");
    const infoBoard = document.getElementById("info-board");
    const infoConfig = document.getElementById("info-config");

    if (infoVariant) infoVariant.textContent = variant || "Not selected";
    if (infoHero) infoHero.textContent = hand.hero;
    if (infoBoard) infoBoard.textContent = hand.board || "none";

    if (variant && this.VARIANT_CONFIG[variant]) {
      const cfg = this.VARIANT_CONFIG[variant];
      if (infoConfig) infoConfig.textContent = `${cfg.players} players, ${cfg.hole_cards} hole cards`;
    } else {
      if (infoConfig) infoConfig.textContent = "—";
    }
  },

  async runEngine() {
    if (this.selectedHandIndex === null) {
      alert("🂠 Select a hand first");
      return;
    }

    const variantSelect = document.getElementById("variant-select");
    const variant = variantSelect ? variantSelect.value : "";
    if (!variant || !this.VARIANT_CONFIG[variant]) {
      alert("🎰 Select a valid game variant");
      return;
    }

    const hand = this.parsedHands[this.selectedHandIndex];
    const resultsEl = document.getElementById("engine-results");
    if (resultsEl) resultsEl.value = "🧮 Calculating equity...\n\nThis may take a few seconds.";

    this.calculating = true;

    try {
      const data = await API.calculateEquity(variant, hand.hero, hand.board || "");
      if (data.ok) {
        if (resultsEl) resultsEl.value = data.output || JSON.stringify(data, null, 2);
      } else {
        if (resultsEl) resultsEl.value = `❌ Error: ${data.error || "Unknown error"}\n\n${data.stderr || ""}`;
      }
    } catch (err) {
      if (resultsEl) resultsEl.value = `❌ Network error: ${err.message}`;
    }

    this.calculating = false;
  },

  clearEngine() {
    this.parsedHands = [];
    this.selectedHandIndex = null;
    this.calculating = false;
    this.render();
  },

  clearInput() {
    const textarea = document.getElementById("engine-import-textarea");
    if (textarea) textarea.value = "";
  }
};
