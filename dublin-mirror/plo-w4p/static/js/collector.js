// Hand Collector page logic

const COLLECTOR_PAGE = {
  parsedHands: [],
  groups: [],

  init() {
    console.log("📋 Initializing hand collector page");
    this.render();
    this.loadLatest();
  },

  destroy() {},

  async loadLatest() {
    try {
      const data = await API.getCollectorLatest();
      if (data.ok && data.raw) {
        const el = document.getElementById("collector-textarea");
        if (el) el.value = data.raw;
      }
    } catch (err) {
      console.log("📋 No existing collector data");
    }
  },

  render() {
    const handsHtml = this.parsedHands.length > 0 ? this.renderHandList() : this.renderEmpty();
    const groupsHtml = this.groups.length > 0 ? this.renderGroups() : "";

    setHTML("#page-content", `
      <section class="summary-grid">
        <div class="summary-card neutral">
          <div class="summary-title">📋✂️ Hands Parsed</div>
          <div class="summary-value">${this.parsedHands.length}</div>
        </div>
        <div class="summary-card positive">
          <div class="summary-title">📦🗂️ Groups</div>
          <div class="summary-value">${this.groups.length}</div>
        </div>
        <div class="summary-card neutral">
          <div class="summary-title">💾📤 Status</div>
          <div class="summary-value">${this.parsedHands.length > 0 ? "Ready" : "Waiting"}</div>
        </div>
      </section>

      <section class="summary-card" style="margin-bottom: 16px;">
        <div class="summary-title">📥✏️ Paste Hand History</div>
        <textarea id="collector-textarea" class="collector-textarea"
          placeholder="Paste hand history text here...&#10;&#10;Supports multiple hands separated by blank lines.&#10;Each hand should contain hero cards, board, and action."></textarea>
        <div class="collector-actions">
          <button data-action="PARSE_HANDS" class="collector-btn parse">📋✂️ Parse Hands</button>
          <button data-action="CLEAR_COLLECTOR" class="collector-btn clear">🗑️ Clear</button>
          <button data-action="SAVE_HANDS" class="collector-btn save" ${this.parsedHands.length === 0 ? "disabled" : ""}>💾📤 Save Hands</button>
          <button data-action="SEND_TO_ENGINE" class="collector-btn engine" ${this.parsedHands.length === 0 ? "disabled" : ""}>🧮🔢 Send to Engine</button>
        </div>
      </section>

      ${groupsHtml}
      ${handsHtml}
    `);
  },

  renderEmpty() {
    return `
      <div class="empty-state">
        <div class="empty-state-icon">📋❌</div>
        <div class="empty-state-message">No hands parsed yet</div>
        <p style="color: var(--text-muted); margin-top: 8px; font-size: 12px;">
          📥 Paste hand history text above and click Parse Hands.
        </p>
      </div>
    `;
  },

  renderGroups() {
    return `
      <section class="summary-card" style="margin-bottom: 16px;">
        <div class="summary-title">📦🗂️ Hand Groups (by timestamp window)</div>
        <div class="group-list">
          ${this.groups.map((group, i) => `
            <div class="group-item">
              <span class="group-label">⏰ Group ${i + 1}</span>
              <span class="group-count">🃏 ${group.hands.length} hands</span>
              <span class="group-time">${group.timestamp || "unknown"}</span>
            </div>
          `).join("")}
        </div>
      </section>
    `;
  },

  renderHandList() {
    const items = this.parsedHands.map((hand, idx) => {
      const variantBadge = hand.variant ? `<span class="hand-variant-badge">🎰 ${hand.variant}</span>` : "";
      const boardText = hand.board || "no board";

      return `
        <div class="hand-list-item ${hand.selected ? 'selected' : ''}" data-action="SELECT_HAND" data-index="${idx}">
          <div class="hand-hero">🂠 ${hand.hero || "Unknown"}</div>
          <div class="hand-board">🃏 Board: ${boardText}</div>
          ${variantBadge}
        </div>
      `;
    }).join("");

    return `
      <section class="summary-card">
        <div class="summary-title">🂠📋 Parsed Hands (${this.parsedHands.length})</div>
        <div class="hand-list-container">
          ${items}
        </div>
      </section>
    `;
  },

  parseHands() {
    const textarea = document.getElementById("collector-textarea");
    if (!textarea || !textarea.value.trim()) {
      alert("📋 Please paste hand history text first");
      return;
    }

    const text = textarea.value.trim();
    this.parsedHands = [];
    this.groups = [];

    // Split by double newlines (hand separator)
    const blocks = text.split(/\n\s*\n/).filter(b => b.trim());

    // Group by 1-second timestamp window
    let currentGroup = { timestamp: null, hands: [] };

    blocks.forEach((block, idx) => {
      const lines = block.split("\n").map(l => l.trim()).filter(l => l);
      if (lines.length === 0) return;

      // Try to extract timestamp from first line
      const tsMatch = lines[0].match(/(\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}:\d{2})/);
      const timestamp = tsMatch ? tsMatch[1] : null;

      // Extract hero hand (look for card patterns like AsKdQcJh)
      let hero = "";
      let board = "";

      for (const line of lines) {
        const clean = line.replace(/\s/g, "");
        // Hero hand: 8-14 chars of card notation
        if (!hero && clean.length >= 8 && clean.length <= 14 && /^[AKQJT2-9][shdc]/i.test(clean)) {
          hero = clean;
        }
        // Board: 6-10 chars of card notation (3-5 cards)
        if (!board && clean.length >= 6 && clean.length <= 10 && /^[AKQJT2-9][shdc]/i.test(clean) && clean !== hero) {
          board = clean;
        }
      }

      // Auto-detect variant from hero hand length
      let variant = null;
      if (hero) {
        const holeCards = hero.length / 2;
        if (holeCards === 4) variant = "PLO4";
        else if (holeCards === 5) variant = "PLO5";
        else if (holeCards === 6) variant = "PLO6";
      }

      const hand = {
        hero: hero || lines[0],
        board: board,
        variant: variant,
        timestamp: timestamp,
        raw: block,
        selected: false
      };

      this.parsedHands.push(hand);

      // Group by timestamp (1-second window)
      if (timestamp) {
        if (!currentGroup.timestamp || timestamp === currentGroup.timestamp) {
          currentGroup.timestamp = timestamp;
          currentGroup.hands.push(hand);
        } else {
          if (currentGroup.hands.length > 0) {
            this.groups.push(currentGroup);
          }
          currentGroup = { timestamp: timestamp, hands: [hand] };
        }
      } else {
        currentGroup.hands.push(hand);
      }
    });

    // Push final group
    if (currentGroup.hands.length > 0) {
      this.groups.push(currentGroup);
    }

    console.log(`📋 Parsed ${this.parsedHands.length} hands in ${this.groups.length} groups`);
    this.render();
  },

  clearCollector() {
    this.parsedHands = [];
    this.groups = [];
    this.render();
    const textarea = document.getElementById("collector-textarea");
    if (textarea) textarea.value = "";
  },

  selectHand(index) {
    this.parsedHands.forEach((h, i) => { h.selected = (i === index); });
    this.render();
  },

  async saveHands() {
    if (this.parsedHands.length === 0) return;

    try {
      const data = await API.saveCollectorHands(this.parsedHands);
      if (data.ok) {
        alert(`✅ Saved ${this.parsedHands.length} hands`);
      }
    } catch (err) {
      console.error("Save failed:", err);
      alert("❌ Failed to save hands");
    }
  },

  sendToEngine() {
    const selected = this.parsedHands.find(h => h.selected);
    if (!selected) {
      alert("📋 Select a hand first, then send to engine");
      return;
    }
    // Store in STORE for engine page to pick up
    STORE.state.engineInput = {
      hero: selected.hero,
      board: selected.board,
      variant: selected.variant,
      raw: selected.raw
    };
    window.location.href = "/engine";
  }
};
