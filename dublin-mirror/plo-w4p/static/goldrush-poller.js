/**
 * GoldRush Smart Poller - Completely Separate from PokerBet
 * Platform: GoldRush
 * API: /api/goldrush/collector/latest
 * Features: Adaptive polling, FLOP auto-trigger, RIVER reset
 */

(() => {
  const PLATFORM = 'GoldRush';
  let pollMs = 1500;
  let timer = null;

  const runtime = {
    lastRawBatch: "",
    lastFlop: null,
    lastRiver: null,
    errorCount: 0,
    platform: PLATFORM
  };

  console.log(`[${PLATFORM}-POLLER] Initializing...`);

  function streetOf(board) {
    if (!board) return "PREFLOP";
    let total = (board.flop || []).length;
    if (board.turn) total += 1;
    if (board.river) total += 1;
    if (total === 3) return "FLOP";
    if (total === 4) return "TURN";
    if (total >= 5) return "RIVER";
    return "PREFLOP";
  }

  function extractFlop(board) {
    if (!board || !board.flop || board.flop.length !== 3) return null;
    return board.flop.slice().sort().join("");
  }

  function clickRunButton() {
    const btn = document.querySelector("button");
    if (btn && btn.textContent.includes("Run")) {
      console.log(`[${PLATFORM}-POLLER] AUTO-CLICKING Run button`);
      btn.click();
    }
  }

  function setTextareaValue(textarea, value) {
    if (!textarea) return;
    textarea.value = value;
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  }

  async function pollLatest() {
    try {
      const response = await fetch('/api/goldrush/collector/latest', {
        credentials: "include",
        cache: "no-store"
      });

      if (!response.ok) {
        runtime.errorCount++;
        console.warn(`[${PLATFORM}-POLLER] Fetch error (${runtime.errorCount})`);
        pollMs = Math.min(5000, 1500 + runtime.errorCount * 500);
        return;
      }

      const data = await response.json();
      const rawBatch = data?.raw_batch || "";

      // Fill textarea
      const textarea = document.querySelector("textarea");
      if (textarea && rawBatch) {
        setTextareaValue(textarea, rawBatch);
      }

      // Detect activity
      const hasData = rawBatch.length > 0;
      pollMs = hasData ? 1500 : 3000;

      // TODO: Add FLOP/RIVER detection when board data available
      // For now, just poll and fill textarea

      runtime.errorCount = 0;
      runtime.lastRawBatch = rawBatch;

    } catch (err) {
      runtime.errorCount++;
      console.error(`[${PLATFORM}-POLLER] Error (${runtime.errorCount}):`, err);
      pollMs = Math.min(5000, 1500 + runtime.errorCount * 500);
    } finally {
      clearTimeout(timer);
      timer = setTimeout(pollLatest, pollMs);
    }
  }

  // Start polling
  console.log(`[${PLATFORM}-POLLER] V2 smart polling started`);
  pollLatest();

  // Export to window for debugging
  window.__goldrushPoller = runtime;
})();
