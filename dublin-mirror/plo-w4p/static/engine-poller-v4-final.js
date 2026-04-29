(() => {
  let pollMs = 1500;
  let timer = null;

  const runtime = {
    lastRawBatch: "",
    lastFlop: null,
    lastRiver: null,
    errorCount: 0
  };

  function scheduleNext(ms = pollMs) {
    clearTimeout(timer);
    timer = setTimeout(pollLatest, ms);
  }

  function streetOf(board) {
    let total = (board?.flop || []).length;
    if (board?.turn) total += 1;
    if (board?.river) total += 1;
    if (total === 3) return "FLOP";
    if (total >= 5) return "RIVER";
    return "PREFLOP";
  }

  function flopKey(board) {
    return (board?.flop || []).join("");
  }

  function riverKey(board) {
    return `${(board?.flop || []).join("")}${board?.turn || ""}${board?.river || ""}`;
  }

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

  async function pollLatest() {
    try {
      const [tableRes, collectorRes] = await Promise.all([
        fetch("/api/table/latest", { credentials: "include", cache: "no-store" }),
        fetch("/api/collector/latest", { credentials: "include", cache: "no-store" })
      ]);

      const tableJson = await tableRes.json();
      const collectorJson = await collectorRes.json();

      const table = tableJson?.table;
      const rawBatch = collectorJson?.raw || collectorJson?.raw_batch || table?.raw_batch || "";
      const board = table?.board || {};
      const street = streetOf(board);
      const textarea = getTextarea();

      if (!table || !textarea) {
        pollMs = 4000;
        return scheduleNext();
      }

      const isActive = !!rawBatch || street !== "PREFLOP";

      if (rawBatch && rawBatch !== runtime.lastRawBatch) {
        setTextareaValue(textarea, rawBatch);
        runtime.lastRawBatch = rawBatch;
      }

      if (street === "FLOP") {
        const fk = flopKey(board);
        if (fk && fk !== runtime.lastFlop) {
          const lines = rawBatch.split('\n').filter(l => l.length > 0);
          const board6 = (board?.flop || []).join("");
          const handCount = lines.filter(l => l.length >= 8 && l !== board6 && !l.startsWith('BOARD:')).length;
          if (handCount < 6) {
            console.log('[AUTO] block trigger: only ' + handCount + '/6 hands');
            return scheduleNext();
          }
          runtime.lastFlop = fk;
          runtime.lastRiver = null;
          clickRunButton();
        }
        pollMs = 1000;
        runtime.errorCount = 0;
        return scheduleNext();
      }

      if (street === "RIVER") {
        const rk = riverKey(board);
        if (rk && rk !== runtime.lastRiver) {
          runtime.lastRiver = rk;
          runtime.lastFlop = null;
          runtime.lastRawBatch = "";
          setTextareaValue(textarea, "");
          fetch("/collector/clear", { method: "POST" }).catch(() => {});
        }
        pollMs = 1500;
        runtime.errorCount = 0;
        return scheduleNext();
      }

      pollMs = isActive ? 2000 : 4000;
      runtime.errorCount = 0;
      scheduleNext();
    } catch (err) {
      console.error("[AUTO] poll failed", err);
      runtime.errorCount += 1;
      pollMs = Math.min(5000, 1500 + runtime.errorCount * 1000);
      scheduleNext();
    }
  }

  if (window.__engineSmartPollStop) {
    window.__engineSmartPollStop();
  }

  window.__engineSmartPollStop = () => {
    clearTimeout(timer);
    console.log("[AUTO] smart poller stopped");
  };

  pollLatest();
  console.log("[AUTO] smart poller started");
})();
