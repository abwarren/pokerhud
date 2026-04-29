(function(){
  'use strict';

  // Cleanup previous instance
  if (window._n4p_timer) { clearInterval(window._n4p_timer); window._n4p_timer = null; }
  if (window._n4p_cmdTimer) { clearTimeout(window._n4p_cmdTimer); window._n4p_cmdTimer = null; }
  if (window._n4p) { clearInterval(window._n4p); window._n4p = null; }
  window._n4p_injected = false;

  var API_BASE = 'https://nuts4poker.com/api';
  var API_KEY = 'trk_prod_1774368827';
  var POLL_MS = { HERO_TURN: 300, HAND_ACTIVE: 400, IDLE: 1000, NO_TABLE: 3000 };
  var CMD_MS  = { HERO_TURN: 100, HAND_ACTIVE: 200, IDLE: 500 };
  var HEARTBEAT_MS = 10000;

  var _mode = 'IDLE';
  var _seatToken = null;
  var _preAction = null;
  var _lastHash = null;
  var _lastSendTime = 0;
  var _n = 0;
  var _errors = 0;
  var _lastError = '';
  var _sessionId = 'n4p_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);

  var RANK_MAP = { 'a':'A', 'k':'K', 'q':'Q', 'j':'J', 't':'T', '10':'T' };

  function log(m) { console.log('[N4P] ' + m); }
  function err(m) { _errors++; _lastError = m; console.error('[N4P] ' + m); }

  // ── Card parser ──────────────────────────────────────────────
  function parseCard(cls) {
    if (!cls) return null;
    var m = cls.match(/icon-layer2_([shdc])(10|[akqjt2-9])_p-c-d/i);
    if (!m) return null;
    var suit = m[1].toLowerCase();
    var rank = m[2].toLowerCase();
    rank = RANK_MAP[rank] || rank;
    return rank + suit;
  }

  // ── Table ID from URL ────────────────────────────────────────
  function getTableId() {
    var url = location.href;
    var m = url.match(/\/tbl\/(\d+)/);
    if (m) return m[1];
    m = url.match(/\/poker\/(\d+)/);
    if (m) return m[1];
    m = url.match(/openGames=(\d+)/);
    if (m) return m[1];
    m = url.match(/game[_-]?id[=\/](\d+)/i);
    if (m) return m[1];
    if (document.querySelector('.player-mini-container-p') || document.querySelector('sg-poker-table-seat')) {
      return 'table_' + (url.match(/(\d+)/) || ['', '0'])[1];
    }
    return null;
  }

  // ── Build full snapshot from PokerBet DOM ────────────────────
  function buildSnapshot() {
    var tableId = getTableId();
    if (!tableId) return null;

    var containers = document.querySelectorAll('.player-mini-container-p');
    if (!containers.length) containers = document.querySelectorAll('sg-poker-table-seat');
    if (!containers.length) return null;

    var fullTable = document.querySelector('.full-table-w-p');
    var szMatch = fullTable ? fullTable.className.match(/player-count-(\d+)/) : null;
    var tableSize = szMatch ? parseInt(szMatch[1]) : 6;

    var dealerEl = document.querySelector('.dealer-icon-view');
    var dMatch = dealerEl ? dealerEl.className.match(/position-(\d+)/) : null;
    var dealerSeat = dMatch ? parseInt(dMatch[1]) : null;

    var potEl = document.querySelector('.pot-w-view-p');
    var potText = potEl ? potEl.innerText : '';
    var pMatch = potText.match(/([\d.,]+)/);
    var potZar = pMatch ? parseFloat(pMatch[1].replace(',', '')) : 0;

    // Board cards (community only)
    var allCardEls = document.querySelectorAll('.single-cart-view-p');
    var boardCards = [];
    for (var i = 0; i < allCardEls.length; i++) {
      var el = allCardEls[i];
      if (el.closest('.player-mini-container-p')) continue;
      var c = parseCard(el.className);
      if (c) boardCards.push(c);
    }

    var street = 'PREFLOP';
    if (boardCards.length >= 5) street = 'RIVER';
    else if (boardCards.length >= 4) street = 'TURN';
    else if (boardCards.length >= 3) street = 'FLOP';

    var seats = [];
    var heroName = null;
    for (var i = 0; i < containers.length; i++) {
      var ct = containers[i];
      var isHero = ct.classList.contains('self-player');
      var isSittingOut = ct.classList.contains('seat-out-v');

      var posMatch = ct.className.match(/position-(\d+)/);
      var seatIdx = posMatch ? parseInt(posMatch[1]) : i;

      var nameEl = ct.querySelector('p.single-win-item-sizes') || ct.querySelector('.player-name');
      var name = nameEl ? (nameEl.innerText || nameEl.textContent || '').trim() : null;
      if (isHero && name) heroName = name;

      var stackEl = ct.querySelector('.player-text-info-p span b');
      var stackText = stackEl ? stackEl.innerText : '';
      var sMatch = stackText.match(/([\d.,]+)/);
      var stackZar = sMatch ? parseFloat(sMatch[1].replace(',', '')) : 0;

      var cardsContainer = ct.querySelector('.carts-container-p');
      var ccMatch = cardsContainer ? cardsContainer.className.match(/cards-count-(\d+)/) : null;
      var cardsCount = ccMatch ? parseInt(ccMatch[1]) : 0;

      var holeCards = [];
      if (isHero) {
        var hcEls = ct.querySelectorAll('.single-cart-view-p');
        for (var j = 0; j < hcEls.length; j++) {
          var hc = parseCard(hcEls[j].className);
          if (hc) holeCards.push(hc);
        }
      }

      var status = 'playing';
      if (isSittingOut) status = 'sitting_out';
      else if (cardsCount === 0 && street !== 'PREFLOP') status = 'folded';

      seats.push({
        seat_index: seatIdx,
        name: name,
        stack_zar: stackZar,
        hole_cards: holeCards,
        cards_count: cardsCount,
        is_hero: isHero,
        is_dealer: seatIdx === dealerSeat,
        status: status
      });
    }

    var foldBtn = document.querySelector('.control-b-view-p.fold-c');
    var checkBtn = document.querySelector('.control-b-view-p.check-c');
    var callBtn = document.querySelector('.control-b-view-p.call-c');
    var cashoutBtn = document.querySelector('.control-b-view-p.cashout-c');

    return {
      player_id: heroName || 'n4p-player',
      session_id: _sessionId,
      table_id: tableId,
      deal_id: boardCards.slice(0, 3).sort().join('') || 'preflop',
      timestamp_utc: new Date().toISOString(),
      variant: 'plo4-' + tableSize + 'max',
      street: street,
      table_size: tableSize,
      dealer_seat: dealerSeat,
      pot_zar: potZar,
      seats: seats,
      board: {
        flop: boardCards.slice(0, 3),
        turn: boardCards[3] || null,
        river: boardCards[4] || null
      },
      action_buttons: {
        visible: !!(foldBtn || checkBtn || callBtn || cashoutBtn),
        fold: !!foldBtn,
        check: !!checkBtn,
        call: !!callBtn,
        cashout: !!cashoutBtn
      },
      source_key: 'n4p'
    };
  }

  // ── State hash for dedup ─────────────────────────────────────
  function stateHash(snap) {
    return JSON.stringify({
      s: snap.seats.map(function(s) { return (s.name||'') + ':' + s.stack_zar + ':' + s.status + ':' + s.hole_cards.join(''); }),
      b: snap.board, p: snap.pot_zar, st: snap.street, d: snap.dealer_seat, a: snap.action_buttons.visible
    });
  }

  // ── Command execution ────────────────────────────────────────
  var BTN_SEL = {
    fold:    '.control-b-view-p.fold-c',
    check:   '.control-b-view-p.check-c',
    call:    '.control-b-view-p.call-c',
    cashout: '.control-b-view-p.cashout-c'
  };

  function clickAction(action) {
    var sel = BTN_SEL[action];
    if (!sel) { log('Unknown action: ' + action); return; }
    var btn = document.querySelector(sel);
    if (btn) { btn.click(); log('Clicked: ' + action); }
    else { log('Button not found: ' + action); }
  }

  function handleCommand(cmd) {
    if (BTN_SEL[cmd.type]) {
      clickAction(cmd.type);
    } else if (cmd.type === 'check_fold') {
      _preAction = 'check_fold';
    } else if (cmd.type === 'check_call') {
      _preAction = 'check_call';
    } else if (cmd.type === 'clear') {
      _preAction = null;
    }
  }

  function runPreAction(buttons) {
    if (!_preAction) return;
    if (_preAction === 'check_fold') {
      if (buttons.check) clickAction('check');
      else if (buttons.fold) clickAction('fold');
    } else if (_preAction === 'check_call') {
      if (buttons.check) clickAction('check');
      else if (buttons.call) clickAction('call');
    }
    _preAction = null;
  }

  // ── Command polling loop ─────────────────────────────────────
  function pollCommands() {
    if (!_seatToken) {
      window._n4p_cmdTimer = setTimeout(pollCommands, CMD_MS[_mode] || 1000);
      return;
    }
    fetch(API_BASE + '/commands/pending?token=' + encodeURIComponent(_seatToken))
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.ok && data.command) {
          log('Command: ' + data.command.type);
          handleCommand(data.command);
          fetch(API_BASE + '/commands/ack', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: _seatToken, command_id: data.command.id })
          });
        }
      })
      .catch(function() { /* silent retry */ })
      .finally(function() {
        window._n4p_cmdTimer = setTimeout(pollCommands, CMD_MS[_mode] || 1000);
      });
  }

  // ── Main snapshot loop ───────────────────────────────────────
  function tick() {
    _n++;
    try {
      var snap = buildSnapshot();

      if (!snap) {
        _mode = 'NO_TABLE';
        window._n4p_timer = setTimeout(tick, POLL_MS.NO_TABLE);
        return;
      }

      if (snap.action_buttons.visible) _mode = 'HERO_TURN';
      else if (snap.street !== 'PREFLOP') _mode = 'HAND_ACTIVE';
      else _mode = 'IDLE';

      var hash = stateHash(snap);
      var now = Date.now();
      var changed = hash !== _lastHash;
      var heartbeat = (now - _lastSendTime) >= HEARTBEAT_MS;

      if (changed || heartbeat) {
        _lastHash = hash;
        _lastSendTime = now;

        fetch(API_BASE + '/snapshot', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
          body: JSON.stringify(snap)
        })
        .then(function(r) {
          if (!r.ok) { err('HTTP ' + r.status); return r.text().then(function(t) { err(t.substring(0, 200)); }); }
          return r.json();
        })
        .then(function(data) {
          if (!data) return;
          if (data.ok && data.seat_token && !_seatToken) {
            _seatToken = data.seat_token;
            log('Connected! Token: ' + _seatToken.substr(0, 8) + '...');
            pollCommands();
          }
        })
        .catch(function(e) { err('Send: ' + e.message); });

        var filled = snap.seats.filter(function(s) { return s.name; }).length;
        log('#' + _n + (heartbeat && !changed ? ' (hb)' : '') +
            ' ' + snap.street + ' pot=R' + snap.pot_zar +
            ' seats=' + filled + '/' + snap.seats.length +
            ' board=' + (snap.board.flop.join('') || '-'));
      }

      if (_preAction && snap.action_buttons.visible) {
        runPreAction(snap.action_buttons);
      }
    } catch(e) {
      err('tick: ' + e.message);
    }

    window._n4p_timer = setTimeout(tick, POLL_MS[_mode] || 2000);
  }

  // ── Start ────────────────────────────────────────────────────
  window._n4p_injected = true;
  window._n4p_buildSnapshot = buildSnapshot;
  window._n4pStatus = function() {
    return { n: _n, errors: _errors, lastError: _lastError, mode: _mode, token: _seatToken ? _seatToken.substr(0,8)+'...' : null, session: _sessionId };
  };

  tick();
  log('v10.0 loaded | Remote: nuts4poker.com/remote | Session: ' + _sessionId);
})();
