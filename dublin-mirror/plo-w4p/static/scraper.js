/**
 * HUD Scraper v3.1 — Full DOM scrape for HUD, HTTP POST cards to N4P
 *
 * Scrapes: cards, board, pot, dealer, stacks, names, actions, street
 * POSTs to N4P: card strings + BOARD: tag only (collector/save format)
 * All state available locally via window._hudScraper.getState()
 */
(function() {
  'use strict';

  if (window._hudScraper) {
    try { window._hudScraper.stop(); } catch(e) {}
    window._hudScraper = null;
  }

  // === CONFIG ===
  var API_URL = 'https://nuts4poker.com/collector/save';
  var POLL_MS = 150;
  var POST_MS = 2000;
  var TABLE_ID = 'A';
  var DEBUG = false;

  // === STATE ===
  var pollTimer = null, postTimer = null, statsTimer = null;
  var lastBoard = '', lastPotText = '', lastDealer = -1;
  var lastActions = new Map();
  var seatStacks = new Map();
  var seatNames = new Map();
  var seatCards = new Map();
  var handId = null, street = 'preflop', eventSeq = 0;
  var pendingSnapshot = null, lastPostHash = '', posting = false;
  var stats = { snapshots: 0, posted: 0, errors: 0 };

  function log() { if (DEBUG) console.log.apply(console, ['[HUD]'].concat(Array.from(arguments))); }
  function warn() { console.warn.apply(console, ['[HUD]'].concat(Array.from(arguments))); }

  function genHandId() {
    return 'H' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2, 5);
  }

  // === CARD PARSING (PokerBet icon-layer2_{suit}{rank}_p-c-d) ===
  function parseCard(cls) {
    if (!cls) return null;
    var tokens = cls.split(/\s+/);
    for (var i = tokens.length - 1; i >= 0; i--) {
      var m = tokens[i].match(/^icon-layer2_([hdcs])(a|k|q|j|10|[2-9])_p-c-d$/i);
      if (m) {
        var rank = {a:'A',k:'K',q:'Q',j:'J','10':'T'}[m[2].toLowerCase()] || m[2].toUpperCase();
        return rank + m[1].toLowerCase();
      }
    }
    return null;
  }

  function getCardsFrom(el) {
    if (!el) return [];
    var cards = [], seen = {};
    var els = el.querySelectorAll('.single-cart-view-p');
    for (var i = 0; i < els.length; i++) {
      var c = parseCard(els[i].getAttribute('class') || '');
      if (c && !seen[c]) { seen[c] = 1; cards.push(c); }
    }
    return cards;
  }

  // === IFRAME DETECTION ===
  function getDoc() {
    var frames = document.querySelectorAll('iframe');
    for (var i = 0; i < frames.length; i++) {
      var src = String(frames[i].src || '');
      if (src.indexOf('skillgames') !== -1 || src.indexOf('18751019') !== -1) {
        try {
          var d = frames[i].contentDocument || (frames[i].contentWindow && frames[i].contentWindow.document);
          if (d) return d;
        } catch(e) {}
      }
    }
    return document;
  }

  function safeText(el) { return (el && (el.innerText || el.textContent) || '').trim(); }
  function parseMoney(t) { return parseFloat((t||'').replace(/[^0-9.,]/g,'').replace(',','.')) || 0; }
  function classNum(cn, prefix) { var m = String(cn||'').match(new RegExp(prefix+'-(\\d+)')); return m ? +m[1] : null; }

  // === DOM SCRAPERS ===

  function scrapeBoard(doc) {
    var el = doc.querySelector('sg-poker-board');
    if (!el) return [];
    var cards = [], seen = {};
    var els = el.querySelectorAll('.single-cart-view-p');
    for (var i = 0; i < els.length; i++) {
      if (els[i].closest('sg-poker-table-seat') || els[i].closest('.player-mini-container-p')) continue;
      var c = parseCard(els[i].getAttribute('class') || '');
      if (c && !seen[c]) { seen[c] = 1; cards.push(c); }
    }
    return cards;
  }

  function scrapePot(doc) {
    var el = doc.querySelector('.pot-w-view-p');
    if (el) return { text: safeText(el), amount: parseMoney(safeText(el)) };
    var sels = ['.pot-amount','.pot-value','.sg-poker-pot','.total-pot'];
    for (var i = 0; i < sels.length; i++) {
      el = doc.querySelector(sels[i]);
      if (el) { var t = safeText(el), a = parseMoney(t); if (a > 0) return { text: t, amount: a }; }
    }
    return { text: '', amount: 0 };
  }

  function scrapeDealer(doc) {
    var el = doc.querySelector('.dealer-icon-view');
    if (el) { var p = classNum(el.className, 'position'); if (p !== null) return p; }
    var btn = doc.querySelector('.dealer-button, [class*="dealer"], .btn-dealer');
    if (btn) {
      var seat = btn.closest('sg-poker-table-seat, .player-mini-container-p');
      if (seat) {
        var all = doc.querySelectorAll('sg-poker-table-seat, .player-mini-container-p');
        for (var i = 0; i < all.length; i++) if (all[i] === seat) return i;
      }
    }
    return -1;
  }

  function scrapeSeats(doc) {
    var results = [];
    var els = doc.querySelectorAll('sg-poker-table-seat');
    if (!els.length) els = doc.querySelectorAll('.player-mini-container-p');

    for (var i = 0; i < els.length; i++) {
      var seat = els[i];
      var d = { seat: i };

      var pos = classNum(seat.className, 'position');
      if (pos !== null) d.seat = pos;

      d.isHero = seat.classList.contains('self-player');
      d.isSittingOut = seat.classList.contains('seat-out-v') || !!seat.querySelector('.seat-out-v');

      // Name
      var nameEl = seat.querySelector('p.single-win-item-sizes') ||
                   seat.querySelector('.player-name, [class*="name"]');
      if (nameEl) { d.name = safeText(nameEl); if (d.name) seatNames.set(d.seat, d.name); }

      // Stack
      var stackEl = seat.querySelector('.player-text-info-p span b') ||
                    seat.querySelector('.player-stack, .stack-value, [class*="stack"]');
      if (stackEl) { d.stack = parseMoney(safeText(stackEl)); if (d.stack > 0) seatStacks.set(d.seat, d.stack); }

      // Hole cards
      var cc = seat.querySelector('.carts-container-p');
      if (cc) {
        var cards = getCardsFrom(cc);
        if (cards.length >= 4) { d.cards = cards.join(''); seatCards.set(d.seat, d.cards); }
      }

      // Action
      var actEl = seat.querySelector('.action-indicator, .player-action, [class*="action-text"]');
      if (actEl) {
        var txt = safeText(actEl).toUpperCase(), amt = parseMoney(safeText(actEl));
        if (txt.indexOf('FOLD') !== -1 || seat.classList.contains('folded')) d.action = 'FOLD';
        else if (txt.indexOf('CHECK') !== -1) d.action = 'CHECK';
        else if (txt.indexOf('ALL') !== -1) { d.action = 'ALL_IN'; d.bet = amt; }
        else if (txt.indexOf('RAISE') !== -1 || txt.indexOf('RE-RAISE') !== -1) { d.action = 'RAISE'; d.bet = amt; }
        else if (txt.indexOf('CALL') !== -1) { d.action = 'CALL'; d.bet = amt; }
        else if (txt.indexOf('BET') !== -1) { d.action = 'BET'; d.bet = amt; }
      }
      if (!d.action && (seat.classList.contains('folded') || seat.querySelector('.folded'))) {
        d.action = 'FOLD'; d.folded = true;
      }
      if (seat.classList.contains('active') || seat.querySelector('.active-turn, .turn-indicator')) {
        d.isActive = true;
      }

      results.push(d);
    }
    return results;
  }

  function detectStreet(board) {
    var n = board.length;
    if (n === 0) return 'preflop';
    if (n === 3) return 'flop';
    if (n === 4) return 'turn';
    return n >= 5 ? 'river' : 'preflop';
  }

  // === SNAPSHOT (full HUD state) ===
  function buildSnapshot(board, pot, dealer, seats) {
    return {
      table_id: TABLE_ID, ts: Date.now(), street: street,
      pot: pot.amount, potText: pot.text,
      board: board, dealer: dealer,
      players: seats.map(function(s) {
        return {
          seat: s.seat, name: s.name||'', stack: s.stack||0,
          cards: s.cards||'', action: s.action||null, bet: s.bet||0,
          isHero: s.isHero||false, isSittingOut: s.isSittingOut||false,
          isActive: s.isActive||false, folded: s.folded||false
        };
      })
    };
  }

  // === N4P POST (cards only) ===
  function hashStr(s) { var h=0; for(var i=0;i<s.length;i++){h=((h<<5)-h)+s.charCodeAt(i);h|=0;} return h; }

  function postToN4P() {
    if (posting || !pendingSnapshot) return;
    var snap = pendingSnapshot;
    var lines = [];
    for (var i = 0; i < snap.players.length; i++) {
      var c = snap.players[i].cards;
      if (c && c.length >= 8) lines.push(c);
    }
    if (!lines.length) return;
    if (snap.board && snap.board.length) lines.push('BOARD:' + snap.board.join(''));
    var text = lines.join('\n');
    var h = hashStr(text);
    if (h === lastPostHash) return;

    posting = true;
    var x = new XMLHttpRequest();
    x.open('POST', API_URL);
    x.setRequestHeader('Content-Type', 'application/json');
    x.timeout = 5000;
    x.onload = function() { posting = false; if (x.status < 300) { lastPostHash = h; stats.posted++; log('POST OK'); } else stats.errors++; };
    x.onerror = x.ontimeout = function() { posting = false; stats.errors++; };
    x.send(JSON.stringify({ text: text, source: 'hud-' + TABLE_ID }));
  }

  // === POLL LOOP (150ms — fast DOM change detection) ===
  function poll() {
    try {
      var doc = getDoc();
      var boardCards = scrapeBoard(doc);
      var pot = scrapePot(doc);
      var dealer = scrapeDealer(doc);
      var seats = scrapeSeats(doc);
      var boardStr = boardCards.join('');
      var newStreet = detectStreet(boardCards);

      // New hand: board cleared
      if (lastBoard.length > 0 && boardStr.length === 0) {
        handId = genHandId(); street = 'preflop'; eventSeq = 0;
        lastActions.clear(); seatCards.clear();
      }
      // New hand: dealer moved
      if (dealer >= 0 && lastDealer >= 0 && dealer !== lastDealer && boardStr.length === 0) {
        if (!handId || eventSeq > 0) {
          handId = genHandId(); street = 'preflop'; eventSeq = 0;
          lastActions.clear(); seatCards.clear();
        }
      }
      // Street change
      if (newStreet !== street && boardStr.length > lastBoard.length) street = newStreet;

      // Change detection
      var changed = false;
      if (boardStr !== lastBoard) changed = true;
      if (pot.text !== lastPotText) changed = true;
      if (dealer !== lastDealer && dealer >= 0) changed = true;
      for (var i = 0; i < seats.length; i++) {
        if (seats[i].action) {
          var key = seats[i].action + ':' + (seats[i].bet||0);
          if (key !== lastActions.get(seats[i].seat)) { changed = true; lastActions.set(seats[i].seat, key); }
        }
      }

      if (changed) {
        pendingSnapshot = buildSnapshot(boardCards, pot, dealer, seats);
        stats.snapshots++;
        eventSeq++;
      }

      lastBoard = boardStr; lastPotText = pot.text;
      if (dealer >= 0) lastDealer = dealer;
    } catch(e) { stats.errors++; warn('poll error:', e); }
  }

  // === PUBLIC API ===
  window._hudScraper = {
    start: function() {
      pollTimer = setInterval(poll, POLL_MS);
      postTimer = setInterval(postToN4P, POST_MS);
      statsTimer = setInterval(function() {
        console.log('[HUD] snapshots=' + stats.snapshots + ' posted=' + stats.posted + ' errors=' + stats.errors + ' street=' + street);
      }, 60000);
      poll();
    },
    stop: function() {
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      if (postTimer) { clearInterval(postTimer); postTimer = null; }
      if (statsTimer) { clearInterval(statsTimer); statsTimer = null; }
    },
    getState: function() {
      return {
        handId: handId, street: street, board: lastBoard, dealer: lastDealer,
        seats: Object.fromEntries(seatNames),
        stacks: Object.fromEntries(seatStacks),
        cards: Object.fromEntries(seatCards),
        snapshot: pendingSnapshot,
        stats: stats
      };
    },
    getSnapshot: function() { return pendingSnapshot; },
    forcePost: function() { postToN4P(); },
    setTable: function(id) { TABLE_ID = id; },
    setApi: function(url) { API_URL = url; },
    debug: function(on) { DEBUG = !!on; }
  };

  window._hudScraper.start();
  console.log('[HUD] v3.1 loaded — poll ' + POLL_MS + 'ms, POST ' + POST_MS + 'ms to ' + API_URL);
})();
