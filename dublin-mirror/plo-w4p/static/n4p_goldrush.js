/**
 * GoldRush Collector - Completely Separate from PokerBet
 * Platform: GoldRush (goldrush.co.za)
 * Endpoint: /api/goldrush/collector/save
 * Storage: /opt/plo-equity/collectors/goldrush/
 */

(function() {
  const PLATFORM = 'GoldRush';
  const API_ENDPOINT = '/api/goldrush/collector/save';
  const POLL_INTERVAL_MS = 2000;

  console.log(`[${PLATFORM}-COLLECTOR] Initializing...`);

  function extractTableData() {
    // TODO: Implement GoldRush-specific table extraction
    // This will depend on GoldRush's specific DOM structure
    
    // Placeholder for now - returns empty to prevent errors
    return {
      raw_batch: '',
      platform: PLATFORM,
      timestamp: Date.now()
    };
  }

  function sendToCollector(data) {
    if (!data.raw_batch || data.raw_batch.trim() === '') {
      return; // Don't send empty data
    }

    fetch(API_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
    .then(r => r.json())
    .then(result => {
      if (result.ok) {
        console.log(`[${PLATFORM}-COLLECTOR] Sent: ${result.file}`);
      } else {
        console.warn(`[${PLATFORM}-COLLECTOR] Error:`, result.error);
      }
    })
    .catch(err => console.error(`[${PLATFORM}-COLLECTOR] Fetch failed:`, err));
  }

  function poll() {
    const data = extractTableData();
    if (data.raw_batch) {
      sendToCollector(data);
    }
  }

  // Start polling
  setInterval(poll, POLL_INTERVAL_MS);
  console.log(`[${PLATFORM}-COLLECTOR] Started (${POLL_INTERVAL_MS}ms interval)`);
})();
