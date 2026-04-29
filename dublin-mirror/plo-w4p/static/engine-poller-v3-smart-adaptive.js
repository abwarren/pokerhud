(() => {
  // ═══════════════════════════════════════════════════════════════════════════
  // SMART ADAPTIVE ENGINE POLLER V3
  // ═══════════════════════════════════════════════════════════════════════════

  const FAST_POLL_MS = 1500;   // Active table
  const SLOW_POLL_MS = 5000;   // Idle table
  const IDLE_THRESHOLD_MS = 30000; // 30s without changes = idle

  const runtime = {
    lastPayload: "",
    lastFlop: null,
    lastRiver: null,
    lastChangeTime: Date.now(),
    currentInterval: FAST_POLL_MS,
    pollTimer: null
  };

  function getTextarea() {
    return document.querySelector('textarea[rows="14"]');
  }

  function setTextareaValue(textarea, value) {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      "value"
    ).set;
    setter.call(textarea, value);
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    textarea.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function clickRunButton() {
    const btn = [...document.querySelectorAll("button")].find(b =>
      /run|calculate|eval|equity/i.test((b.innerText || "").trim())
    );
    if (btn) {
      btn.click();
      console.log("[AUTO] Engine triggered");
    }
  }

  function extractBoard(table) {
    const board = table?.board || {};
    const flop = board.flop || [];
    const turn = board.turn || "";
    const river = board.river || "";
    return { flop, turn, river };
  }

  function streetOf(board) {
    let total = (board.flop || []).length;
    if (board.turn) total += 1;
    if (board.river) total += 1;

    if (total === 3) return "FLOP";
    if (total === 4) return "TURN";
    if (total >= 5) return "RIVER";
    return "PREFLOP";
  }

  function flopKey(board) {
    return (board.flop || []).join("");
  }

  function riverKey(board) {
    return `${(board.flop || []).join("")}${board.turn || ""}${board.river || ""}`;
  }

  function isTableActive(payload, board) {
    // Table is active if:
    // - Has player data (payload not empty)
    // - Has board cards
    // - Recently changed
    const hasPlayers = payload && payload.trim().length > 0;
    const hasBoard = board.flop && board.flop.length > 0;
    const recentChange = (Date.now() - runtime.lastChangeTime) < IDLE_THRESHOLD_MS;
    
    return hasPlayers || hasBoard || recentChange;
  }

  function adjustPollSpeed(isActive) {
    const newInterval = isActive ? FAST_POLL_MS : SLOW_POLL_MS;
    
    if (newInterval !== runtime.currentInterval) {
      runtime.currentInterval = newInterval;
      
      // Restart timer with new interval
      if (runtime.pollTimer) {
        clearInterval(runtime.pollTimer);
        runtime.pollTimer = setInterval(pollLatest, newInterval);
      }
      
      console.log(`[POLL] Speed adjusted: ${isActive ? 'ACTIVE' : 'IDLE'} (${newInterval}ms)`);
    }
  }

  async function pollLatest() {
    try {
      // Fetch board structure for street detection
      const tableRes = await fetch("/api/table/latest", {
        method: "GET",
        credentials: "include",
        cache: "no-store"
      });

      const tableJson = await tableRes.json();
      if (!tableJson?.ok || !tableJson?.table) return;

      const table = tableJson.table;
      const textarea = getTextarea();
      if (!textarea) return;

      // Fetch raw collector batch (canonical payload)
      const collectorRes = await fetch("/api/collector/latest", {
        method: "GET",
        credentials: "include",
        cache: "no-store"
      });

      const collectorJson = await collectorRes.json();
      if (!collectorJson?.ok) return;

      // Use raw batch directly (no reconstruction)
      const payload = collectorJson.raw || "";
      const board = extractBoard(table);
      const street = streetOf(board);

      // Check if anything changed
      const payloadChanged = payload && payload !== runtime.lastPayload;
      const isActive = isTableActive(payload, board);

      // Inject raw batch into textarea if changed
      if (payloadChanged) {
        setTextareaValue(textarea, payload);
        runtime.lastPayload = payload;
        runtime.lastChangeTime = Date.now();
        console.log(`[POLL] Payload updated (${payload.split('\\n').length} lines)`);
      }

      // Adjust polling speed based on activity
      adjustPollSpeed(isActive);

      // FLOP: auto-run once
      if (street === "FLOP") {
        const fk = flopKey(board);
        if (fk && fk !== runtime.lastFlop) {
          runtime.lastFlop = fk;
          runtime.lastRiver = null;
          runtime.lastChangeTime = Date.now();
          clickRunButton();
          console.log(`[AUTO] FLOP detected: ${fk} -> engine run`);
        }
        return;
      }

      // TURN: manual only
      if (street === "TURN") {
        return;
      }

      // RIVER: reset
      if (street === "RIVER") {
        const rk = riverKey(board);
        if (rk && rk !== runtime.lastRiver) {
          runtime.lastRiver = rk;
          runtime.lastFlop = null;
          runtime.lastChangeTime = Date.now();
          setTextareaValue(textarea, "");
          runtime.lastPayload = "";
          console.log(`[AUTO] RIVER detected: ${rk} -> reset`);
        }
        return;
      }

      // PREFLOP: clear river state
      if (street === "PREFLOP") {
        if (runtime.lastRiver) {
          runtime.lastRiver = null;
          runtime.lastChangeTime = Date.now();
        }
      }
    } catch (err) {
      console.error("[POLL] Error:", err);
    }
  }

  // Stop existing poller if any
  if (window.__enginePoller) {
    clearInterval(window.__enginePoller);
  }

  // Start smart adaptive polling
  runtime.pollTimer = setInterval(pollLatest, runtime.currentInterval);
  pollLatest(); // Run immediately
  
  window.__enginePoller = runtime.pollTimer;
  console.log(`[POLL] Smart adaptive poller V3 started (${FAST_POLL_MS}ms active, ${SLOW_POLL_MS}ms idle)`);
})();
