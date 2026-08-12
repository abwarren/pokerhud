/* ── PokerHUD: content.js ──
 * Multi-site content script. Loads a selector profile from src/selectors/*.json
 * based on location.hostname (exact match in profile.domains, else a
 * betconstruct fallback for poker-web.*.co.za hosts), then detects the table,
 * scrapes a snapshot tagged with the profile's site name, and renders the HUD.
 */

(() => {
  'use strict';

  const DEBUG = true;
  const log = (...args) => DEBUG && console.log('[POKERHUD]', ...args);

  const POLL_INTERVAL_MS = 2500;
  const SELECTOR_FILES = ['evenbet.json', 'betconstruct.json'];
  const FALLBACK_HOST_RE = /^poker-web\..+\.co\.za$/;

  let profile = null;
  let isOnTable = false;
  let hudContainer = null;

  // ── Profile loading / selection ──
  async function loadProfiles() {
    const profiles = [];
    for (const file of SELECTOR_FILES) {
      try {
        const resp = await fetch(chrome.runtime.getURL('src/selectors/' + file));
        if (resp.ok) {
          profiles.push(await resp.json());
        } else {
          log('Profile fetch failed for', file, resp.status);
        }
      } catch (e) {
        log('Failed to load selector profile', file, e);
      }
    }
    return profiles;
  }

  function selectProfile(profiles) {
    const host = location.hostname;
    for (const p of profiles) {
      if (p.domains && p.domains.includes(host)) return p;
    }
    // Fallback: betconstruct profile for any poker-web.*.co.za host
    if (FALLBACK_HOST_RE.test(host)) {
      const bc = profiles.find(p => p.site === 'pokerbet');
      if (bc) {
        log('Using fallback betconstruct profile for', host);
        return bc;
      }
    }
    return null;
  }

  function detectTable() {
    const canvases = document.querySelectorAll('canvas');
    for (const c of canvases) {
      if (c.width > 200 && c.height > 200) return true;
    }
    const containers = document.querySelectorAll(
      '[class*="table"],[class*="Table"],[class*="seat"],[class*="Seat"],' +
      '[class*="player"],[class*="Player"]'
    );
    if (containers.length >= 3) return true;
    if (profile && document.querySelectorAll(profile.seatSel).length >= 2) return true;
    if (location.hash.includes('table') || location.hash.includes('game')) return true;
    return false;
  }

  // ── DOM-scraping path (canvasTable=false, e.g. EvenBet/SunBet) ──
  function scrapeDomTable(snapshot) {
    const seats = document.querySelectorAll(profile.seatSel);
    for (const seat of seats) {
      const name = seat.querySelector(profile.nameSel)?.textContent?.trim() || '';
      if (!name || name.length === 0 || name.length >= 30) continue;
      const stackText = seat.querySelector(profile.stackSel)?.textContent?.trim() || '';
      const chips = stackText ? parseFloat(stackText.replace(/[^0-9.]/g, '')) : null;
      snapshot.players.push({
        name,
        position: (seat.className.match(/\bs-(\d+)\b/) || [])[1] || seat.getAttribute('data-position') || '',
        chips: Number.isFinite(chips) ? chips : null,
        cards: [],
        isHero: !!seat.querySelector('.self-player'),
      });
    }

    const potEl = document.querySelector(profile.potSel);
    if (potEl) {
      const m = potEl.textContent.trim().match(/(\d[\d,.]*)/);
      if (m) snapshot.pot = parseFloat(m[1].replace(/[, ]/g, ''));
    }

    const boardEls = document.querySelectorAll(profile.boardSel);
    snapshot.board = Array.from(boardEls)
      .map(c => c.textContent.trim() || c.getAttribute('title') || c.getAttribute('alt') || '')
      .filter(Boolean);
  }

  // ── Canvas/fallback path (canvasTable=true, e.g. BetConstruct) ──
  function scrapeCanvasTable(snapshot) {
    const seatSelectors = profile
      ? profile.seatSel.split(',').map(s => s.trim())
      : ['[class*="seat"][class*="player"]', '[class*="Seat"]',
         '[class*="player-box"]', '[data-player]'];
    const nameSel = profile ? profile.nameSel : '[class*="name"],[class*="Name"],p:first-child';
    const stackSel = profile ? profile.stackSel : '[class*="chips"],[class*="Chips"],[class*="stack"]';

    for (const sel of seatSelectors) {
      const seats = document.querySelectorAll(sel);
      if (seats.length >= 2) {
        for (const seat of seats) {
          const name = seat.querySelector(nameSel)?.textContent?.trim();
          const chips = seat.querySelector(stackSel)?.textContent?.trim();
          if (name && name.length > 0 && name.length < 30) {
            snapshot.players.push({
              name, position: seat.getAttribute('data-position') || '',
              chips: chips ? parseInt(chips.replace(/[^0-9]/g, '')) : null,
              cards: [], isHero: false,
            });
          }
        }
        if (snapshot.players.length >= 2) break;
      }
    }

    if (snapshot.players.length < 2) {
      const lines = document.body.innerText.split('\n').map(l => l.trim()).filter(l => l);
      for (const line of lines) {
        const m = line.match(/^([A-Za-z][A-Za-z0-9._ -]{2,20})\s+(?:ZAR|R)?\s*(\d[\d, ]*)/);
        if (m && !snapshot.players.find(p => p.name === m[1].trim())) {
          snapshot.players.push({
            name: m[1].trim(),
            chips: parseInt(m[2].replace(/[, ]/g, '')),
            position: '', cards: [], isHero: false,
          });
        }
      }
    }

    const potSels = profile
      ? profile.potSel.split(',').map(s => s.trim())
      : ['[class*="pot"]', '[class*="Pot"]', '[class*="total-pot"]'];
    for (const sel of potSels) {
      const el = document.querySelector(sel);
      if (el) {
        const m = el.textContent.trim().match(/(\d[\d, ]*)/);
        if (m) { snapshot.pot = parseInt(m[1].replace(/[, ]/g, '')); break; }
      }
    }

    const boardSels = profile
      ? [profile.boardSel]
      : ['[class*="board"] [class*="card"],[class*="Board"] [class*="card"]',
         '[class*="community"]'];
    for (const sel of boardSels) {
      const cards = document.querySelectorAll(sel);
      if (cards.length >= 1) {
        snapshot.board = Array.from(cards).map(c => c.textContent.trim()).filter(Boolean);
        break;
      }
    }
  }

  function scrapeTable() {
    const snapshot = {
      site: profile ? profile.site : 'unknown',
      url: location.href,
      timestamp: Date.now(),
      gameType: null, stakes: null, players: [],
      pot: null, board: [], heroCards: [], handId: null,
    };

    if (profile && !profile.canvasTable) {
      scrapeDomTable(snapshot);
    } else {
      scrapeCanvasTable(snapshot);
    }

    // EvenBet exposes a real hand id via .game-id; otherwise keep an auto id.
    const gameIdEl = document.querySelector('.game-id');
    if (gameIdEl && gameIdEl.textContent.trim()) {
      snapshot.handId = gameIdEl.textContent.trim().replace(/^#/, '');
    } else {
      snapshot.handId = 'auto_' + Math.floor(Date.now() / 1000);
    }
    return snapshot;
  }

  function createHUD() {
    if (hudContainer) return;
    hudContainer = document.createElement('div');
    hudContainer.id = 'pokerbet-hud-container';
    document.body.appendChild(hudContainer);
    log('HUD injected');
  }

  function sendToBackground(data) {
    try { chrome.runtime.sendMessage({ type: 'TABLE_SNAPSHOT', data }); } catch (e) {}
  }

  function poll() {
    const onTable = detectTable();
    if (onTable !== isOnTable) {
      isOnTable = onTable;
      log('Table: ' + isOnTable);
      if (isOnTable) createHUD();
    }
    if (isOnTable) {
      const snap = scrapeTable();
      sendToBackground(snap);
      window.dispatchEvent(new CustomEvent('pokerbet-hud-snapshot', { detail: snap }));
    }
  }

  async function init() {
    const profiles = await loadProfiles();
    profile = selectProfile(profiles);
    log('Profile:', profile ? profile.site : 'none', 'for', location.hostname);

    isOnTable = detectTable();
    if (isOnTable) createHUD();
    new MutationObserver(() => {
      const now = detectTable();
      if (now !== isOnTable) { isOnTable = now; if (now) createHUD(); }
    }).observe(document.body, { childList: true, subtree: true });
    setInterval(poll, POLL_INTERVAL_MS);
    setTimeout(poll, 1000);
    log('Content script initialized');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
