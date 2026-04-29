(() => {
  const POLL_MS = 1500;

  const runtime = {
    lastPayload: "",
    lastFlop: null,
    lastRiver: null
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
    if (btn) btn.click();
  }

  function buildPayload(table) {
    const seats = table?.seats || [];
    return seats
      .map(seat => (seat.hole_cards || []).join(""))
      .filter(Boolean)
      .join("\n");
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

  async function pollLatest() {
    try {
      const res = await fetch("/api/table/latest", {
        method: "GET",
        credentials: "include",
        cache: "no-store"
      });

      const json = await res.json();
      if (!json?.ok || !json?.table) return;

      const table = json.table;
      const textarea = getTextarea();
      if (!textarea) return;

      const payload = buildPayload(table);
      const board = extractBoard(table);
      const street = streetOf(board);

      if (payload && payload !== runtime.lastPayload) {
        setTextareaValue(textarea, payload);
        runtime.lastPayload = payload;
      }

      if (street === "FLOP") {
        const fk = flopKey(board);
        if (fk && fk !== runtime.lastFlop) {
          runtime.lastFlop = fk;
          runtime.lastRiver = null;
          clickRunButton();
          console.log("[AUTO] FLOP detected -> engine run once");
        }
        return;
      }

      if (street === "TURN") {
        console.log("[AUTO] TURN detected -> manual only");
        return;
      }

      if (street === "RIVER") {
        const rk = riverKey(board);
        if (rk && rk !== runtime.lastRiver) {
          runtime.lastRiver = rk;
          runtime.lastFlop = null;
          setTextareaValue(textarea, "");
          runtime.lastPayload = "";
          console.log("[AUTO] RIVER detected -> reset");
        }
        return;
      }

      if (street === "PREFLOP") {
        runtime.lastRiver = null;
      }
    } catch (err) {
      console.error("Polling failed:", err);
    }
  }

  if (window.__enginePoller) {
    clearInterval(window.__enginePoller);
  }

  pollLatest();
  window.__enginePoller = setInterval(pollLatest, POLL_MS);
  console.log(`[AUTO] Engine poller started (${POLL_MS}ms)`);
})();
