/* ── PokerBet HUD: background.js (Service Worker) ── */
import { StatsEngine } from '../lib/stats.js';

const DEBUG = true;
const log = (...args) => DEBUG && console.log('[POKERBET-BG]', ...args);

const statsEngine = new StatsEngine();
let tablesSeen = new Set();
let totalSnapshots = 0;
let lastSnapshot = null;
let dbUrl = 'http://localhost:8899';

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  switch (msg.type) {
    case 'TABLE_SNAPSHOT':
      handleSnapshot(msg.data, sender);
      sendResponse({ ok: true });
      break;
    case 'GET_STATS':
      sendResponse(getSummary());
      break;
    case 'SET_DB_URL':
      dbUrl = msg.url;
      chrome.storage.local.set({ dbUrl: msg.url });
      sendResponse({ ok: true });
      break;
    default:
      sendResponse({ ok: false, error: 'unknown type' });
  }
  return true;
});

function handleSnapshot(data, sender) {
  if (!data) return;
  totalSnapshots++;
  lastSnapshot = data;
  tablesSeen.add(sender?.tab?.id || 'unknown');

  if (data.players && data.players.length > 0) {
    for (const p of data.players) {
      statsEngine.ingest({
        actions: [{
          player: p.name,
          type: 'observe',
          street: 'preflop',
          timestamp: data.timestamp,
        }]
      });
    }
  }

  if (totalSnapshots % 4 === 0) {
    syncToDashboard().catch(() => {});
  }
  updateBadge();
}

function getSummary() {
  const allPlayers = statsEngine.getPlayers();
  return {
    totalHands: statsEngine.hands.length,
    totalPlayers: allPlayers.length,
    tablesSeen: tablesSeen.size,
    lastUpdate: lastSnapshot?.timestamp || null,
    myStats: null,
    players: allPlayers.map(name => statsEngine.getStats(name)).filter(Boolean),
  };
}

function updateBadge() {
  const count = statsEngine.getPlayers().length;
  chrome.action.setBadgeText({ text: count > 0 ? String(count) : '' });
  chrome.action.setBadgeBackgroundColor({ color: '#238636' });
}

async function syncToDashboard() {
  const summary = getSummary();
  if (summary.totalPlayers === 0) return;
  try {
    const resp = await fetch(dbUrl + '/api/hud-sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        timestamp: Date.now(),
        players: summary.players,
        totalHands: summary.totalHands,
      }),
    });
    if (resp.ok) log('Synced');
  } catch (e) {}
}

chrome.storage.local.get('dbUrl', (result) => {
  if (result.dbUrl) dbUrl = result.dbUrl;
  log('Background worker started');
});

setInterval(() => { syncToDashboard().catch(() => {}); }, 30000);
