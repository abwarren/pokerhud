// W4P Injectable v16 - PLO Remote Table Control (hero-only: .self-player class ONLY, no fallbacks)
// Paste into skillgames iframe console, or: fetch('https://potlimitomaha.xyz/w4p.js').then(r=>r.text()).then(eval)
// Scrapes ALL seats, sends structured snapshots with button detection, polls commands, clicks buttons
// No chrome.runtime deps — pure fetch-based

(function(){
  'use strict';

  // ── Cleanup prior instances ──────────────────────────────────
  if (window._w4p_timer) { clearTimeout(window._w4p_timer); window._w4p_timer = null; }
  if (window._w4p_cmdTimer) { clearTimeout(window._w4p_cmdTimer); window._w4p_cmdTimer = null; }
  if (window._w4p_bbTimer) { clearInterval(window._w4p_bbTimer); window._w4p_bbTimer = null; }
  if (window._w4p) { clearInterval(window._w4p); window._w4p = null; }
  window._w4p_injected = false;

  // ── Config ───────────────────────────────────────────────────
  var API_BASE = 'https://potlimitomaha.xyz/api';
  var API_KEY  = 'trk_prod_1774368827';

  // v15: tightened polling — faster detection, faster commands
  var POLL_MS = { HERO_TURN: 300, HAND_ACTIVE: 300, IDLE: 300, NO_TABLE: 2000 };
  var CMD_MS  = { HERO_TURN: 150, HAND_ACTIVE: 150, IDLE: 150 };
  var HEARTBEAT_MS = 8000;
  var CASHOUT_POLL_MS = 75;  // hyper-poll interval when cashout preselected

  var _mode = 'IDLE';
  var _seatToken = null;
  var _preAction = null;    // 'check_fold' | 'check_call' | null
  var _lastHash = null;
  var _lastSendTime = 0;
  var _n = 0;
  var _sessionId = 'w4p_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
  var _lastButtons = null;
  var _cashoutPre = false;   // when true, hyper-poll for cashout DOM element
  var _cashoutTimer = null;
  var _lastBoardLen = 0;     // track board cards for new hand detection

  var RANK_MAP = { 'a':'A', 'k':'K', 'q':'Q', 'j':'J', 't':'T', '10':'T' };

  // ── Action button selectors (PokerBet / BetConstruct DOM) ───
  var BTN_SEL = {
    fold:         '.control-b-view-p.fold-c',
    check:        '.control-b-view-p.check-c',
    call:         '.control-b-view-p.call-c',
    raise:        '.control-b-view-p.raise-c',
    bet:          '.control-b-view-p.bet-c',
    cashout:      '.control-b-view-p.cash_out-c',
    allin:        '.control-b-view-p.all_in-c',
    show:         '.control-b-view-p.show-c',
    run_it_twice: '.control-b-view-p.run_it_twice-c',
    resume_hand:  '.control-b-view-p.resume_hand-c',
    back_to_game: '.control-b-view-p.back_to_game-c'
  };

  // ── Detected buttons cache (populated each getAvailableActions call) ──
  var _detectedBtns = {};

  function buildCssPath(el) {
    if (!el) return '';
    var parts = [];
    var cur = el;
    while (cur && cur !== document.body && parts.length < 5) {
      var tag = cur.tagName.toLowerCase();
      if (cur.id) { parts.unshift('#' + cur.id); break; }
      var cls = '';
      if (cur.className && typeof cur.className === 'string') {
        var cc = cur.className.trim().split(/\s+/).filter(function(c) {
          return c && c.indexOf('ng-') !== 0 && c !== 'active' && c !== 'hover';
        }).slice(0, 4);
        if (cc.length) cls = '.' + cc.join('.');
      }
      parts.unshift(tag + cls);
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  }

  function detectSliderPresets() {
    var presetItems = document.querySelectorAll(
      'sg-poker-betting-slider .limits-buttons-v-p li, ' +
      'sg-poker-betting-slider li, .limits-buttons-v-p li, ' +
      '[class*="limit"] li'
    );
    for (var i = 0; i < presetItems.length; i++) {
      var el = presetItems[i];
      if (el.offsetParent === null && el.offsetWidth === 0) continue;
      var txt = (el.textContent || '').trim().toLowerCase();
      var pName = null;
      if (/\bmax\b|all[\s-]*in/i.test(txt)) pName = 'preset_max';
      else if (/\bmin\b/i.test(txt)) pName = 'preset_min';
      else if (/\bpot\b/i.test(txt) && !/half/i.test(txt) && !/1\/2/i.test(txt)) pName = 'preset_pot';
      else if (/half|1\/2/i.test(txt)) pName = 'preset_half';
      if (pName && !_detectedBtns[pName]) {
        var rect = el.getBoundingClientRect();
        _detectedBtns[pName] = {
          el: el, selector: buildCssPath(el),
          text: txt.substring(0, 30),
          x: Math.round(rect.x + rect.width / 2),
          y: Math.round(rect.y + rect.height / 2)
        };
      }
    }
  }

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
    if (m) return 'pb_' + m[1];
    m = url.match(/\/poker\/(\d+)/);
    if (m) return 'pb_' + m[1];
    m = url.match(/openGames=(\d+)/);
    if (m) return 'pb_' + m[1];
    m = url.match(/game[_-]?id[=\/](\d+)/i);
    if (m) return 'pb_' + m[1];
    if (url.indexOf('skillgames') !== -1 || url.indexOf('18751019') !== -1) {
      var idm = url.match(/(\d{4,})/);
      return 'pb_' + (idm ? idm[1] : 'sg');
    }
    if (document.querySelector('.player-mini-container-p') || document.querySelector('sg-poker-table-seat')) {
      var idm2 = url.match(/(\d{3,})/);
      return 'pb_' + (idm2 ? idm2[1] : '0');
    }
    return null;
  }

  // ── Player bet (chips near seat) ──────────────────────────────
  function getPlayerBet(seatNum) {
    var chipEl = document.querySelector('sg-chips-view.player-' + seatNum + '-chips .chip-container-view-p p i');
    if (chipEl) {
      var val = (chipEl.innerText || chipEl.textContent || '').trim();
      if (val) {
        var n = parseFloat(val.replace(/[^0-9.]/g, ''));
        return isNaN(n) ? 0 : n;
      }
    }
    return 0;
  }

  // ── Available actions (hero only — gated on .active turn) ────
  function getAvailableActions() {
    var heroSeat = document.querySelector('sg-poker-table-seat.self-player') || document.querySelector('.player-mini-container-p.self-player');
    if (heroSeat) {
      var turnActive = heroSeat.classList.contains('active') || !!heroSeat.querySelector('.active-turn');
      if (!turnActive) { _detectedBtns = {}; return []; }
    }
    _detectedBtns = {};
    var avail = [];

    // Primary: scan ALL known selectors (including allin) + cache element refs
    for (var name in BTN_SEL) {
      var btn = document.querySelector(BTN_SEL[name]);
      if (btn && (btn.offsetParent !== null || btn.offsetWidth > 0)) {
        avail.push(name);
        var rect = btn.getBoundingClientRect();
        _detectedBtns[name] = {
          el: btn, selector: BTN_SEL[name],
          text: (btn.textContent || '').trim().substring(0, 30),
          x: Math.round(rect.x + rect.width / 2),
          y: Math.round(rect.y + rect.height / 2)
        };
      }
    }

    // Also detect slider presets if slider is open
    detectSliderPresets();

    // Fallback: scan ALL visible control elements by class
    if (avail.length === 0) {
      var actionMap = {fold:'fold', check:'check', call:'call', raise:'raise', bet:'bet',
                       cashout:'cashout', show:'show', allin:'all_in'};
      var candidates = document.querySelectorAll('[class*="fold"], [class*="check"], [class*="call"], [class*="raise"], [class*="bet-c"], [class*="cash_out"], [class*="all_in"]');
      for (var i = 0; i < candidates.length; i++) {
        var el = candidates[i];
        if (el.offsetParent === null && el.offsetWidth === 0) continue;
        var cls = el.className.toLowerCase();
        for (var key in actionMap) {
          var searchTerm = actionMap[key] || key;
          if (cls.indexOf(searchTerm) !== -1 && avail.indexOf(key) === -1) {
            avail.push(key);
            var frect = el.getBoundingClientRect();
            _detectedBtns[key] = {
              el: el, selector: buildCssPath(el),
              text: (el.textContent || '').trim().substring(0, 30),
              x: Math.round(frect.x + frect.width / 2),
              y: Math.round(frect.y + frect.height / 2)
            };
          }
        }
      }
      if (avail.length > 0 && _n <= 5) {
        console.log('[W4P] actions via fallback:', avail.join(','));
      }
    }

    // Log detected buttons on first few ticks for debugging
    if (avail.length > 0 && _n <= 3) {
      var btnList = [];
      for (var bk in _detectedBtns) {
        btnList.push(bk + '=' + _detectedBtns[bk].selector);
      }
      console.log('[W4P] detected buttons: ' + btnList.join(' | '));
    }

    return avail;
  }

  // ── Button detection (exact selectors + state for remote) ───
  function detectButtons() {
    var result = { actions: [], presets: [], slider: null };

    // Only detect when hero is active
    var heroSeat = document.querySelector('sg-poker-table-seat.self-player') || document.querySelector('.player-mini-container-p.self-player');
    if (heroSeat) {
      var turnActive = heroSeat.classList.contains('active') || !!heroSeat.querySelector('.active-turn');
      if (!turnActive) { _lastButtons = result; return result; }
    }

    // 1. Known action buttons — scan BTN_SEL for visible ones
    for (var name in BTN_SEL) {
      if (name === 'allin') continue;
      var el = document.querySelector(BTN_SEL[name]);
      if (el && (el.offsetParent !== null || el.offsetWidth > 0)) {
        var text = (el.innerText || el.textContent || '').trim();
        var amtMatch = text.match(/([\d,]+\.?\d*)/);
        result.actions.push({
          action: name,
          text: text,
          amount: amtMatch ? parseFloat(amtMatch[1].replace(/,/g, '')) : null,
          selector: BTN_SEL[name]
        });
      }
    }
    // Check native all-in button separately
    var allinEl = document.querySelector(BTN_SEL.allin);
    if (allinEl && (allinEl.offsetParent !== null || allinEl.offsetWidth > 0)) {
      var allinText = (allinEl.innerText || allinEl.textContent || '').trim();
      var allinAmt = allinText.match(/([\d,]+\.?\d*)/);
      result.actions.push({
        action: 'allin',
        text: allinText,
        amount: allinAmt ? parseFloat(allinAmt[1].replace(/,/g, '')) : null,
        selector: BTN_SEL.allin
      });
    }

    // 2. Presets (min/half/pot/max) from slider panel
    var PRPAT = { min: /\bmin\b/i, half: /\bhalf\b|1\/2/i, pot: /\bpot\b/i, max: /\bmax\b|all[\s-]?in/i };
    var presetEls = document.querySelectorAll(
      'sg-poker-betting-slider li, .limits-buttons-v-p li, [class*="limit"] li, [class*="preset"] li');
    for (var p = 0; p < presetEls.length; p++) {
      var pel = presetEls[p];
      if (pel.offsetParent === null && pel.offsetWidth === 0) continue;
      var ptext = (pel.innerText || pel.textContent || '').trim();
      if (!ptext) continue;
      var label = 'custom';
      for (var pk in PRPAT) {
        if (PRPAT[pk].test(ptext)) { label = pk; break; }
      }
      var pamtMatch = ptext.match(/([\d,]+\.?\d*)/);
      result.presets.push({
        label: label, text: ptext,
        amount: pamtMatch ? parseFloat(pamtMatch[1].replace(/,/g, '')) : null,
        index: p
      });
    }

    // 3. Slider state (range + text/number input)
    var rangeEl = document.querySelector('sg-poker-betting-slider input[type="range"]') || document.querySelector('input[type="range"]');
    var amtEl = document.querySelector('sg-poker-betting-slider input[type="number"]') || document.querySelector('sg-poker-betting-slider input[type="text"]');
    if (!amtEl) {
      var ins = document.querySelectorAll('input[type="number"], input[type="text"]');
      for (var ii = 0; ii < ins.length; ii++) {
        if ((ins[ii].offsetParent !== null || ins[ii].offsetWidth > 0) && !ins[ii].closest('sg-buy-in-modal')) {
          amtEl = ins[ii]; break;
        }
      }
    }
    if (rangeEl || amtEl) {
      result.slider = {
        visible: (rangeEl && rangeEl.offsetParent !== null) || (amtEl && amtEl.offsetParent !== null),
        current: amtEl ? parseFloat(amtEl.value) || 0 : (rangeEl ? parseFloat(rangeEl.value) || 0 : 0),
        min: rangeEl ? parseFloat(rangeEl.min) || 0 : null,
        max: rangeEl ? parseFloat(rangeEl.max) || 0 : null,
        step: rangeEl ? parseFloat(rangeEl.step) || 1 : null
      };
    }

    _lastButtons = result;
    return result;
  }

  // ── Build full snapshot — ALL seats ──────────────────────────
  function buildSnapshot() {
    var tableId = getTableId();
    if (!tableId) {
      if (_n <= 5 || _n % 30 === 0)
        console.log('[W4P] no tableId');
      return null;
    }

    var containers = document.querySelectorAll('sg-poker-table-seat');
    if (!containers.length) containers = document.querySelectorAll('.player-mini-container-p');
    if (!containers.length) {
      if (_n <= 5 || _n % 30 === 0)
        console.log('[W4P] no seat containers');
      return null;
    }

    // Dealer position
    var dealerEl = document.querySelector('.dealer-icon-view');
    var dMatch = dealerEl ? dealerEl.className.match(/position-(\d+)/) : null;
    var dealerSeat = dMatch ? parseInt(dMatch[1]) : null;

    // Pot amount
    var potEl = document.querySelector('.pot-w-view-p') || document.querySelector('.pot-amount') || document.querySelector('.total-pot');
    var potText = potEl ? (potEl.innerText || potEl.textContent || '') : '';
    var pMatch = potText.match(/([\d.,]+)/);
    var potZar = pMatch ? parseFloat(pMatch[1].replace(',', '')) : 0;

    // Board cards (community cards only)
    var boardCards = [];
    var boardEl = document.querySelector('sg-poker-board');
    if (boardEl) {
      var bcEls = boardEl.querySelectorAll('.single-cart-view-p');
      for (var i = 0; i < bcEls.length; i++) {
        if (bcEls[i].closest('sg-poker-table-seat') || bcEls[i].closest('.player-mini-container-p')) continue;
        var c = parseCard(bcEls[i].className);
        if (c) boardCards.push(c);
      }
    }
    if (boardCards.length < 3) {
      var allCardEls = document.querySelectorAll('.single-cart-view-p');
      boardCards = [];
      for (var i = 0; i < allCardEls.length; i++) {
        if (allCardEls[i].closest('.player-mini-container-p') || allCardEls[i].closest('sg-poker-table-seat')) continue;
        var c2 = parseCard(allCardEls[i].className);
        if (c2) boardCards.push(c2);
      }
    }

    var street = 'PREFLOP';
    if (boardCards.length >= 5) street = 'RIVER';
    else if (boardCards.length >= 4) street = 'TURN';
    else if (boardCards.length >= 3) street = 'FLOP';

    var buttons = detectButtons();
    var avail = buttons.actions.map(function(a) { return a.action; });

    // ── Detect active seat (whose turn to act) from PokerBet DOM ──
    var activePlayerName = null;
    for (var ai = 0; ai < containers.length; ai++) {
      var act = containers[ai];
      if (act.classList.contains('active') || act.querySelector('.active-turn')) {
        var anEl = act.querySelector('p.single-win-item-sizes') || act.querySelector('.player-name');
        activePlayerName = anEl ? (anEl.innerText || anEl.textContent || '').trim() : null;
        if (!activePlayerName) activePlayerName = null;
        break;
      }
    }

    // ── Scrape ALL seats ────────────────────────────────────────
    var seats = [];
    var heroName = null;

    for (var i = 0; i < containers.length; i++) {
      var ct = containers[i];
      var isHero = ct.classList.contains('self-player') || !!ct.querySelector('.self-player');

      var posMatch = ct.className.match(/position-(\d+)/);
      var seatIdx = posMatch ? parseInt(posMatch[1]) : i;

      // Player name
      var nameEl = ct.querySelector('p.single-win-item-sizes') || ct.querySelector('.player-name');
      var name = nameEl ? (nameEl.innerText || nameEl.textContent || '').trim() : null;
      if (!name || name === '') name = null;

      // Stack
      var stackEl = ct.querySelector('.player-text-info-p span b') || ct.querySelector('.player-text-info-p b') || ct.querySelector('.player-stack');
      var stackText = stackEl ? (stackEl.innerText || stackEl.textContent || '') : '';
      var sMatch = stackText.match(/([\d.,]+)/);
      var stackZar = sMatch ? parseFloat(sMatch[1].replace(',', '')) : 0;

      // Hole cards — try to parse for ALL seats (fallback hero detection)
      var holeCards = [];
      var cardsContainer = ct.querySelector('.carts-container-p');
      var hcEls = (cardsContainer || ct).querySelectorAll('.single-cart-view-p');
      for (var j = 0; j < hcEls.length; j++) {
        var hc = parseCard(hcEls[j].className);
        if (hc) holeCards.push(hc);
      }

      // REMOVED: hole-cards fallback was marking villains as hero during showdown
      // when all players' cards are revealed face-up. The .self-player class is
      // the ONLY reliable hero signal — it's set by the poker client on the
      // player's own seat and never appears on villains even at showdown.

      if (isHero) heroName = name;

      // HERO-ONLY: skip all non-hero seats. Each bot sends only itself.
      // Other bots at the same table send their own snapshots.
      if (!isHero) continue;

      // Status detection
      var sittingOut = ct.classList.contains('seat-out-v') || !!ct.querySelector('.seat-out-v');
      var isFolded = ct.classList.contains('folded') || !!ct.querySelector('.folded');
      var isActive = ct.classList.contains('active') || !!ct.querySelector('.active-turn');

      var status = 'playing';
      if (sittingOut) status = 'sitting_out';
      else if (isFolded) status = 'folded';
      else if (holeCards.length === 0 && street !== 'PREFLOP') status = 'folded';

      seats.push({
        seat_index:        seatIdx,
        name:              name,
        stack_zar:         stackZar,
        hole_cards:        holeCards,
        is_hero:           true,
        is_self_player:    true,
        is_dealer:         seatIdx === dealerSeat,
        status:            status,
        sitting_out:       sittingOut,
        is_active:         isActive,
        available_actions: avail,
        bet:               getPlayerBet(seatIdx)
      });
    }

    // Must have found hero
    if (!heroName) {
      if (_n <= 5 || _n % 30 === 0) {
        var seatClasses = [];
        for (var d = 0; d < containers.length; d++) {
          var dct = containers[d];
          var dname = dct.querySelector('p.single-win-item-sizes') || dct.querySelector('.player-name');
          var dnameText = dname ? dname.textContent.trim() : 'EMPTY';
          seatClasses.push(dnameText + ':' + dct.className.replace(/\s+/g, '.'));
        }
        console.log('[W4P] no hero | ' + containers.length + ' seats | ' + seatClasses.join(' | '));
      }
      return null;
    }

    return {
      table_id:      tableId,
      bot_id:        heroName,
      session_id:    _sessionId,
      seats:         seats,
      board: {
        flop:  boardCards.slice(0, 3),
        turn:  boardCards[3] || null,
        river: boardCards[4] || null
      },
      pot_zar:       potZar,
      dealer_seat:   dealerSeat,
      street:        street,
      variant:       'plo',
      buttons:       buttons,
      available_actions: avail,
      active_player: activePlayerName,
      ts:            new Date().toISOString(),
      source_key:    'w4p_inject'
    };
  }

  // ── State hash for dedup ─────────────────────────────────────
  function stateHash(snap) {
    var hero = null;
    for (var i = 0; i < snap.seats.length; i++) {
      if (snap.seats[i].is_hero) { hero = snap.seats[i]; break; }
    }
    if (!hero) return '';
    return JSON.stringify({
      si: hero.seat_index, n: hero.name, st: hero.stack_zar,
      hc: hero.hole_cards.join(''), stat: hero.status,
      act: hero.is_active, aa: hero.available_actions.join(','),
      btn: snap.buttons ? snap.buttons.actions.map(function(a) { return a.action + ':' + (a.amount || ''); }).join(',') : '',
      b: snap.board, p: snap.pot_zar, str: snap.street, d: snap.dealer_seat
    });
  }

  // ── Snapshot response handler ────────────────────────────────
  function handleSnapshotResponse(data) {
    if (data.ok) {
      if (data.seat_token) {
        if (!_seatToken) {
          console.log('[W4P] Connected! seat_no=' + data.seat_no + ' token=' + data.seat_token.substr(0, 8) + '...');
          _seatToken = data.seat_token;
          pollCommands();
        } else {
          _seatToken = data.seat_token;
        }
      }
    } else {
      console.log('[W4P] API error:', data.error);
    }
  }

  // ── Send snapshot (direct fetch) ─────────────────────────────
  function sendSnapshot(snap) {
    fetch(API_BASE + '/snapshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body: JSON.stringify(snap)
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { handleSnapshotResponse(data); })
    .catch(function(e) {
      console.log('[W4P] fetch error:', e.message);
    });
  }

  // ── Set raise slider amount ──────────────────────────────────
  function setRaiseAmount(amount) {
    if (!amount || amount <= 0) return false;
    var slider = document.querySelector('sg-poker-betting-slider input[type="range"]');
    if (!slider) slider = document.querySelector('input[type="range"]');
    if (slider) {
      var nativeSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nativeSet.call(slider, String(amount));
      slider.dispatchEvent(new Event('input', {bubbles: true}));
      slider.dispatchEvent(new Event('change', {bubbles: true}));
      return true;
    }
    var inputs = document.querySelectorAll('input[type="number"], input[type="text"]');
    for (var i = 0; i < inputs.length; i++) {
      if (inputs[i].offsetParent !== null && !inputs[i].closest('sg-buy-in-modal')) {
        var nativeSet2 = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSet2.call(inputs[i], String(amount));
        inputs[i].dispatchEvent(new Event('input', {bubbles: true}));
        inputs[i].dispatchEvent(new Event('change', {bubbles: true}));
        return true;
      }
    }
    return false;
  }

  // ── Click a DOM button by selector ───────────────────────────
  function clickSel(sel) {
    var btn = document.querySelector(sel);
    if (btn && (btn.offsetParent !== null || btn.offsetWidth > 0)) {
      btn.click();
      return true;
    }
    return false;
  }

  // ── Open raise slider (ensures slider is visible) ────────────
  function openRaiseSlider(cb) {
    var slider = document.querySelector('sg-poker-betting-slider input[type="range"]') || document.querySelector('input[type="range"]');
    if (slider && slider.offsetParent !== null) {
      cb(); // slider already open
      return true;
    }
    var raiseBtn = document.querySelector(BTN_SEL.raise) || document.querySelector(BTN_SEL.bet);
    if (!raiseBtn || (raiseBtn.offsetParent === null && raiseBtn.offsetWidth === 0)) {
      console.log('[W4P] Raise/bet button not visible');
      return false;
    }
    raiseBtn.click();
    setTimeout(cb, 300);
    return true;
  }

  // ── Set slider to specific value (no confirm) ───────────────
  // Uses execCommand('insertText') to simulate real typing — triggers
  // Angular's change detection which ignores programmatic value sets.
  function setSliderValue(val) {
    val = String(val);
    var numVal = parseFloat(val);
    if (isNaN(numVal) || numVal <= 0) return;

    // ── Strategy A: execCommand on text/number input ──
    // Simulates real keyboard input → fires genuine InputEvent → Angular sees it
    var amtInput = document.querySelector('sg-poker-betting-slider input[type="number"]')
      || document.querySelector('sg-poker-betting-slider input[type="text"]');
    if (!amtInput) {
      var inputs = document.querySelectorAll('input[type="number"], input[type="text"]');
      for (var i = 0; i < inputs.length; i++) {
        if (inputs[i].offsetParent !== null && !inputs[i].closest('sg-buy-in-modal')) {
          amtInput = inputs[i];
          break;
        }
      }
    }
    if (amtInput) {
      amtInput.focus();
      // Select all existing text
      if (amtInput.select) amtInput.select();
      else if (amtInput.setSelectionRange) amtInput.setSelectionRange(0, amtInput.value.length);
      // Try execCommand (fires real browser InputEvent that Angular picks up)
      var execOk = document.execCommand('insertText', false, val);
      if (!execOk || amtInput.value !== val) {
        // Fallback: native setter + InputEvent (not plain Event)
        var nativeSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSet.call(amtInput, val);
        try {
          amtInput.dispatchEvent(new InputEvent('input', {bubbles: true, data: val, inputType: 'insertText'}));
        } catch(e) {
          amtInput.dispatchEvent(new Event('input', {bubbles: true}));
        }
        amtInput.dispatchEvent(new Event('change', {bubbles: true}));
      }
      console.log('[W4P] setSlider: text input → ' + amtInput.value + ' (wanted ' + val + ')');
    }

    // ── Strategy B: Range slider with pointer + mouse events ──
    var slider = document.querySelector('sg-poker-betting-slider input[type="range"]') || document.querySelector('input[type="range"]');
    if (slider) {
      var nativeSet2 = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nativeSet2.call(slider, val);
      slider.dispatchEvent(new Event('input', {bubbles: true}));
      slider.dispatchEvent(new Event('change', {bubbles: true}));

      // Pointer/mouse drag to correct position
      var maxAttr = parseFloat(slider.getAttribute('max') || slider.max) || 100;
      var minAttr = parseFloat(slider.getAttribute('min') || slider.min) || 0;
      var rect = slider.getBoundingClientRect();
      if (rect.width > 0 && maxAttr > minAttr) {
        var ratio = Math.min(Math.max((numVal - minAttr) / (maxAttr - minAttr), 0), 1);
        var posX = rect.left + ratio * rect.width;
        var midY = rect.top + rect.height / 2;
        // PointerEvent (modern Angular components use these)
        try {
          slider.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true, cancelable:true, clientX:rect.left, clientY:midY, pointerId:1, pointerType:'mouse'}));
          slider.dispatchEvent(new PointerEvent('pointermove', {bubbles:true, cancelable:true, clientX:posX, clientY:midY, pointerId:1, pointerType:'mouse'}));
          slider.dispatchEvent(new PointerEvent('pointerup',   {bubbles:true, cancelable:true, clientX:posX, clientY:midY, pointerId:1, pointerType:'mouse'}));
        } catch(e) {}
        // MouseEvent fallback
        slider.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, clientX:rect.left, clientY:midY}));
        slider.dispatchEvent(new MouseEvent('mousemove', {bubbles:true, cancelable:true, clientX:posX, clientY:midY}));
        slider.dispatchEvent(new MouseEvent('mouseup',   {bubbles:true, cancelable:true, clientX:posX, clientY:midY}));
      }
    }
  }

  // ── Set slider to MAX (no confirm — BET button confirms) ────
  function selectMax() {
    openRaiseSlider(function() {
      // Fresh detect presets now that slider is open
      detectSliderPresets();

      // 1. Use detected MAX preset element if available
      if (_detectedBtns.preset_max && _detectedBtns.preset_max.el) {
        var cached = _detectedBtns.preset_max.el;
        if (cached.offsetParent !== null || cached.offsetWidth > 0) {
          cached.click();
          var ci0 = cached.querySelectorAll('*');
          for (var k = 0; k < ci0.length; k++) ci0[k].click();
          console.log('[W4P] MAX via detected: "' + _detectedBtns.preset_max.text + '" sel=' + _detectedBtns.preset_max.selector);
          return;
        }
      }

      // 2. Scan preset items for MAX/ALL-IN text
      var presetItems = document.querySelectorAll('sg-poker-betting-slider .limits-buttons-v-p li, sg-poker-betting-slider li, .limits-buttons-v-p li, [class*="limit"] li, [class*="preset"] li, [class*="amount"] li');
      for (var pi = 0; pi < presetItems.length; pi++) {
        var txt = (presetItems[pi].textContent || '').trim().toLowerCase();
        if (/max|all[\s-]*in/i.test(txt)) {
          presetItems[pi].click();
          var inners = presetItems[pi].querySelectorAll('*');
          for (var ci = 0; ci < inners.length; ci++) inners[ci].click();
          console.log('[W4P] MAX preset clicked: "' + txt + '"');
          return;
        }
      }

      // 3. Last preset fallback (usually max)
      var lastPreset = document.querySelector('sg-poker-betting-slider .limits-buttons-v-p > ul > li:last-child, .limits-buttons-v-p li:last-child');
      if (lastPreset && lastPreset.offsetParent !== null) {
        lastPreset.click();
        var inners2 = lastPreset.querySelectorAll('*');
        for (var ci2 = 0; ci2 < inners2.length; ci2++) inners2[ci2].click();
        console.log('[W4P] MAX: clicked last preset');
        return;
      }

      // 4. Direct slider max: set range input to its max attribute
      var slider = document.querySelector('sg-poker-betting-slider input[type="range"]') || document.querySelector('input[type="range"]');
      if (slider) {
        var maxAttr = slider.getAttribute('max') || slider.max;
        if (maxAttr) { setSliderValue(maxAttr); console.log('[W4P] MAX: slider→max=' + maxAttr); return; }
      }
      console.log('[W4P] MAX: no preset or slider found');
    });
    return true;
  }

  // ── Set slider to MIN (no confirm) ──────────────────────────
  function selectMin() {
    openRaiseSlider(function() {
      // 1. Try MIN preset button
      var presetItems = document.querySelectorAll('sg-poker-betting-slider .limits-buttons-v-p li, sg-poker-betting-slider li, .limits-buttons-v-p li, [class*="limit"] li, [class*="preset"] li, [class*="amount"] li');
      for (var pi = 0; pi < presetItems.length; pi++) {
        var txt = (presetItems[pi].textContent || '').trim().toLowerCase();
        if (/min/i.test(txt)) {
          presetItems[pi].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
          var inner = presetItems[pi].querySelector('span, button, a, div, p');
          if (inner) inner.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
          console.log('[W4P] MIN selected: "' + txt + '"');
          return;
        }
      }
      // 2. First-child fallback
      var firstPreset = document.querySelector('sg-poker-betting-slider .limits-buttons-v-p > ul > li:first-child');
      if (firstPreset && firstPreset.offsetParent !== null) {
        firstPreset.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
        console.log('[W4P] MIN selected (first-child)');
        return;
      }
      // No preset found — log and bail (no slider manipulation)
      console.log('[W4P] MIN: no preset button found');
    });
    return true;
  }

  // ── Click POT preset button (no confirm) ─────────────────────
  function selectPot() {
    openRaiseSlider(function() {
      // 1. Try POT preset button
      var presetItems = document.querySelectorAll('sg-poker-betting-slider .limits-buttons-v-p li, sg-poker-betting-slider li, .limits-buttons-v-p li, [class*="limit"] li, [class*="preset"] li, [class*="amount"] li');
      for (var pi = 0; pi < presetItems.length; pi++) {
        var txt = (presetItems[pi].textContent || '').trim().toLowerCase();
        if (/pot/i.test(txt) && !/half/i.test(txt) && !/1\/2/i.test(txt)) {
          presetItems[pi].click();
          var inners = presetItems[pi].querySelectorAll('*');
          for (var ci = 0; ci < inners.length; ci++) inners[ci].click();
          console.log('[W4P] POT preset clicked: "' + txt + '"');
          return;
        }
      }
      // No preset found — log and bail (no slider manipulation)
      console.log('[W4P] POT: no preset button found');
    });
    return true;
  }

  // ── Set slider to custom amount (no confirm) ────────────────
  function selectAmount(amount) {
    openRaiseSlider(function() {
      setSliderValue(amount);
      console.log('[W4P] Bet size set to ' + amount);
    });
    return true;
  }

  // ── Set slider + confirm (one-shot for raise/pot) ───────────
  function raiseAmount(amount) {
    openRaiseSlider(function() {
      setSliderValue(amount);
      console.log('[W4P] Raise amount=' + amount + ' + confirm');
      setTimeout(function() { confirmRaise(); }, 400);
    });
    return true;
  }

  // ── Execute ALL-IN: native button → preset+confirm → max slider+confirm ──
  function executeAllin() {
    // 1. Try native all-in button first (fastest path)
    var allinBtn = document.querySelector(BTN_SEL.allin);
    if (allinBtn && (allinBtn.offsetParent !== null || allinBtn.offsetWidth > 0)) {
      allinBtn.click();
      console.log('[W4P] ALL-IN: native .all_in-c clicked');
      return true;
    }
    // No fallback — exact selector only per DOM rule
    console.log("[W4P] ALL-IN: .all_in-c not visible, skipping");
    return true;
  }

  // ── Confirm raise: click the confirm/execute button ──────────
  function confirmRaise() {
    // 1. Try cached detected raise element first (exact ref from last scan)
    if (_detectedBtns.raise && _detectedBtns.raise.el) {
      var cached = _detectedBtns.raise.el;
      if (cached.offsetParent !== null || cached.offsetWidth > 0) {
        cached.click();
        console.log('[W4P] Confirm: detected raise clicked (' + _detectedBtns.raise.selector + ')');
        return;
      }
    }
    // 2. Try cached detected bet element
    if (_detectedBtns.bet && _detectedBtns.bet.el) {
      var cachedBet = _detectedBtns.bet.el;
      if (cachedBet.offsetParent !== null || cachedBet.offsetWidth > 0) {
        cachedBet.click();
        console.log('[W4P] Confirm: detected bet clicked (' + _detectedBtns.bet.selector + ')');
        return;
      }
    }
    // 3. Fallback: fresh querySelector for raise
    var raiseBtn = document.querySelector(BTN_SEL.raise);
    if (raiseBtn && (raiseBtn.offsetParent !== null || raiseBtn.offsetWidth > 0)) {
      raiseBtn.click();
      console.log('[W4P] Confirm: raise button clicked');
      return;
    }
    // 4. Fallback: fresh querySelector for bet
    var betBtn = document.querySelector(BTN_SEL.bet);
    if (betBtn && (betBtn.offsetParent !== null || betBtn.offsetWidth > 0)) {
      betBtn.click();
      console.log('[W4P] Confirm: bet button clicked');
      return;
    }
    // 5. BetConstruct raise-confirm <i> element
    var execBtn = document.querySelector('.f-right-column-p > ul > li:nth-child(3) > div > p > i');
    if (execBtn && execBtn.offsetParent !== null) { execBtn.click(); console.log('[W4P] Confirm: exec <i> clicked'); return; }
    // 6. Raise row itself
    var alt = document.querySelector('.f-right-column-p > ul > li:nth-child(3)');
    if (alt && alt.offsetParent !== null) { alt.click(); console.log('[W4P] Confirm: raise row clicked'); return; }
    console.log('[W4P] Confirm: no confirm button found');
  }

  // ── Click simple action button ───────────────────────────────
  function clickAction(action, amount) {
    var key = action.toLowerCase().replace(/[\s-]/g, '_');

    // BET = if amount provided, set it first then confirm; otherwise just confirm
    if (key === 'bet') {
      if (amount) {
        selectAmount(amount);
        setTimeout(function() { confirmRaise(); }, 600);
      } else {
        confirmRaise();
      }
      return true;
    }
    // RAISE with amount = set slider then confirm
    if (key === 'raise') {
      if (amount) {
        openRaiseSlider(function() {
          setSliderValue(amount);
          setTimeout(function() { confirmRaise(); }, 300);
        });
        return true;
      }
      // No amount = just open the slider
      return openRaiseSlider(function(){});
    }
    // ALL-IN = set max + confirm in one action
    if (key === 'allin') {
      return executeAllin();
    }

    var sel = BTN_SEL[key];
    if (!sel) { console.log('[W4P] Unknown action:', action); return false; }

    var btn = document.querySelector(sel);
    if (btn && (btn.offsetParent !== null || btn.offsetWidth > 0)) {
      btn.click();
      console.log('[W4P] Clicked:', action);
      return true;
    }
    console.log('[W4P] Button not visible:', action);
    return false;
  }

  // ── Buy-in handling (v15: faster timeouts) ───────────────────
  function handleBuyin(cmd) {
    var mode = (cmd.type || '').replace('buyin_', '').replace('rebuy_', '');
    // Try sg-buy-in-modal first (if already open)
    var modal = document.querySelector('sg-buy-in-modal');
    if (modal && modal.offsetParent !== null) {
      doBuyin(modal, mode, cmd.amount);
      return;
    }
    // Try clicking hero avatar to open buy-in
    var hero = document.querySelector('.player-mini-container-p.self-player');
    if (hero) {
      hero.click();
      setTimeout(function() {
        var m = document.querySelector('sg-buy-in-modal');
        if (m) doBuyin(m, mode, cmd.amount);
        else console.log('[W4P] Buy-in modal did not appear');
      }, 400);
    } else {
      // Fallback: generic buy-in button search
      var buyBtns = document.querySelectorAll('button, [class*="buy"], [class*="rebuy"]');
      for (var i = 0; i < buyBtns.length; i++) {
        var txt = (buyBtns[i].textContent || '').trim().toLowerCase();
        if (/buy.?in|rebuy|top.?up/i.test(txt) && buyBtns[i].offsetParent !== null) {
          buyBtns[i].click();
          setTimeout(function() {
            var m = document.querySelector('sg-buy-in-modal');
            if (m) doBuyin(m, mode, cmd.amount);
          }, 400);
          return;
        }
      }
    }
  }

  function doBuyin(modal, mode, amount) {
    if (mode === 'max') {
      var maxBtn = modal.querySelector('.modal-balance-v li:nth-child(2) .last-v-p button');
      if (maxBtn && maxBtn.offsetParent !== null) {
        maxBtn.click();
        console.log('[W4P] Buy-in MAX clicked');
      }
    } else if (mode === 'min') {
      var minBtn = modal.querySelector('.modal-balance-v li:nth-child(2) .mini-button-view-m:first-child button');
      if (minBtn && minBtn.offsetParent !== null) {
        minBtn.click();
        console.log('[W4P] Buy-in MIN clicked');
      }
    } else if (amount) {
      // Custom amount — set slider/input
      var inputs = modal.querySelectorAll('input[type="number"], input[type="range"], input[type="text"]');
      for (var i = 0; i < inputs.length; i++) {
        if (inputs[i].offsetParent !== null) {
          var nativeSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          nativeSet.call(inputs[i], String(amount));
          inputs[i].dispatchEvent(new Event('input', {bubbles: true}));
          inputs[i].dispatchEvent(new Event('change', {bubbles: true}));
          console.log('[W4P] Buy-in amount set:', amount);
          break;
        }
      }
    }
    // Confirm
    setTimeout(function() {
      var submit = modal.querySelector('.modal-button-container button');
      if (submit && submit.offsetParent !== null) {
        submit.click();
        console.log('[W4P] Buy-in confirmed');
      }
    }, 300);
  }

  // ── Command handler ──────────────────────────────────────────
  function handleCommand(cmd) {
    var action = (cmd.type || cmd.command || '').toLowerCase();
    console.log('[W4P] CMD:', action, cmd.amount ? 'amt=' + cmd.amount : '');

    // ── Pre-actions & buy-in ──
    if (action === 'buyin' || action === 'rebuy_max' || action === 'rebuy_min' || action === 'buyin_max' || action === 'buyin_min') {
      handleBuyin(cmd); return;
    }
    if (action === 'cashout_preselect') { _cashoutPre = true; console.log('[W4P] CASHOUT preselected — hyper-polling .cash_out-c'); return; }
    if (action === 'cashout_clear')     { _cashoutPre = false; console.log('[W4P] CASHOUT preselect cleared'); return; }
    if (action === 'check_fold') { _preAction = 'check_fold'; console.log('[W4P] Pre-action: CHECK/FOLD'); return; }
    if (action === 'check_call') { _preAction = 'check_call'; console.log('[W4P] Pre-action: CHECK/CALL'); return; }
    if (action === 'clear')      { _preAction = null;          console.log('[W4P] Pre-action cleared');    return; }

    // ── Pure native button clicks — mirror PokerBet exactly ──
    var DIRECT = {
      fold:    '.control-b-view-p.fold-c',
      check:   '.control-b-view-p.check-c',
      call:    '.control-b-view-p.call-c',
      cashout: '.control-b-view-p.cash_out-c',
      show:    '.control-b-view-p.show-c'
    };
    if (DIRECT[action]) {
      var btn = document.querySelector(DIRECT[action]);
      if (btn && (btn.offsetParent !== null || btn.offsetWidth > 0)) {
        btn.click(); console.log('[W4P] Clicked native:', action);
      } else { console.log('[W4P] Button not visible:', action); }
      return;
    }

    // ALL-IN: click native all-in button
    if (action === 'allin' || action === 'all-in' || action === 'all_in') {
      var allinBtn = document.querySelector('.control-b-view-p.all_in-c');
      if (allinBtn && (allinBtn.offsetParent !== null || allinBtn.offsetWidth > 0)) {
        allinBtn.click(); console.log('[W4P] Clicked native: ALL-IN');
      } else { console.log('[W4P] ALL-IN: .all_in-c not visible, skipping'); }
      return;
    }

    // RAISE / BET — with amount handling
    if (action === 'raise' || action === 'bet') {
      if (cmd.amount) {
        // Amount specified: open slider → set amount → confirm
        openRaiseSlider(function() {
          setSliderValue(cmd.amount);
          setTimeout(function() { confirmRaise(); }, 400);
        });
        console.log('[W4P] ' + action + ' amount=' + cmd.amount);
      } else {
        // No amount: just click the button
        var rb = document.querySelector('.control-b-view-p.raise-c') || document.querySelector('.control-b-view-p.bet-c');
        if (rb && (rb.offsetParent !== null || rb.offsetWidth > 0)) { rb.click(); console.log('[W4P] Clicked native:', action); }
      }
      return;
    }

    // POT: click RAISE → POT preset → RAISE
    if (action === 'pot') { clickPresetAndConfirm(/^pot$/i); return; }

    // MAX: click RAISE → MAX preset → RAISE
    if (action === 'max' || action === 'raise_max') { clickPresetAndConfirm(/max|all/i); return; }

    // MIN: click RAISE → MIN preset → RAISE
    if (action === 'min' || action === 'raise_min') { clickPresetAndConfirm(/^min$/i); return; }

    // HALF: click RAISE → 1/2 preset → RAISE
    if (action === 'half' || action === '1/2') { clickPresetAndConfirm(/1\/2|half/i); return; }

    // CLICK: direct selector click (used by remote with detected selectors)
    if (action === 'click' && cmd.selector) {
      var clickEl = document.querySelector(cmd.selector);
      if (clickEl && (clickEl.offsetParent !== null || clickEl.offsetWidth > 0)) {
        clickEl.click();
        console.log('[W4P] Clicked selector:', cmd.selector);
      } else {
        console.log('[W4P] Selector not found/hidden:', cmd.selector);
      }
      return;
    }

    console.log('[W4P] Unknown command:', action);
  }

  // ── Click preset in PokerBet slider panel then confirm ──
  // Human flow: click RAISE → click preset → click RAISE
  function clickPresetAndConfirm(presetRegex) {
    var raiseBtn = document.querySelector('.control-b-view-p.raise-c') || document.querySelector('.control-b-view-p.bet-c');
    if (!raiseBtn || (raiseBtn.offsetParent === null && raiseBtn.offsetWidth === 0)) {
      console.log('[W4P] No raise/bet button visible'); return;
    }
    raiseBtn.click();
    console.log('[W4P] Opened slider panel');
    setTimeout(function() {
      var presets = document.querySelectorAll('sg-poker-betting-slider .limits-buttons-v-p li, .limits-buttons-v-p li');
      var clicked = false;
      for (var i = 0; i < presets.length; i++) {
        var txt = (presets[i].textContent || '').trim();
        if (presetRegex.test(txt)) {
          presets[i].click();
          console.log('[W4P] Clicked preset: ' + txt);
          clicked = true; break;
        }
      }
      if (!clicked && /max|all/i.test(presetRegex.source) && presets.length > 0) {
        presets[presets.length - 1].click();
        console.log('[W4P] Clicked last preset (MAX fallback)');
      }
      setTimeout(function() {
        var confirmBtn = document.querySelector('.control-b-view-p.raise-c') || document.querySelector('.control-b-view-p.bet-c');
        if (confirmBtn && (confirmBtn.offsetParent !== null || confirmBtn.offsetWidth > 0)) {
          confirmBtn.click(); console.log('[W4P] Confirmed raise');
        }
      }, 600);
    }, 500);
  }

  function runPreAction(avail) {
    if (!_preAction) return;
    if (_preAction === 'check_fold') {
      if (avail.indexOf('check') !== -1) clickAction('check');
      else if (avail.indexOf('fold') !== -1) clickAction('fold');
    } else if (_preAction === 'check_call') {
      if (avail.indexOf('check') !== -1) clickAction('check');
      else if (avail.indexOf('call') !== -1) clickAction('call');
    }
    _preAction = null;
  }

  // ── Command polling loop ─────────────────────────────────────
  function pollCommands() {
    if (!_seatToken) {
      window._w4p_cmdTimer = setTimeout(pollCommands, CMD_MS[_mode] || 500);
      return;
    }

    fetch(API_BASE + '/commands/pending?token=' + encodeURIComponent(_seatToken))
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.ok && data.command) {
          handleCommand(data.command);
          // Acknowledge immediately
          fetch(API_BASE + '/commands/ack', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: _seatToken, command_id: data.command.id })
          }).catch(function(){});
        }
      })
      .catch(function(){});

    window._w4p_cmdTimer = setTimeout(pollCommands, CMD_MS[_mode] || 500);
  }

  // ── Auto-untick "Wait for Big Blind" ─────────────────────────
  function untickWaitBB() {
    var cbs = document.querySelectorAll('input[type="checkbox"]');
    for (var i = 0; i < cbs.length; i++) {
      if (cbs[i].checked) {
        var label = cbs[i].parentElement ? cbs[i].parentElement.textContent : '';
        if (/wait.*big\s*blind|big\s*blind/i.test(label)) {
          cbs[i].click();
          console.log('[W4P] Unticked: Wait for Big Blind');
        }
      }
    }
    var toggles = document.querySelectorAll('.check-box-view-p.active, .toggle-switch.active, [class*="wait-bb"].active');
    for (var j = 0; j < toggles.length; j++) {
      var txt = toggles[j].textContent || '';
      if (/wait.*big\s*blind|big\s*blind/i.test(txt)) {
        toggles[j].click();
      }
    }
  }

  // ── Main snapshot loop ───────────────────────────────────────
  function tryCashout() {
    if (!_cashoutPre) return;
    var btn = document.querySelector('.control-b-view-p.cash_out-c');
    if (btn && (btn.offsetParent !== null || btn.offsetWidth > 0)) {
      btn.click();
      _cashoutPre = false;
      console.log('[W4P] CASHOUT executed via preselect');
    }
  }

  function tick() {
    _n++;
    var snap = buildSnapshot();

    if (!snap) {
      _mode = 'NO_TABLE';
      window._w4p_timer = setTimeout(tick, POLL_MS.NO_TABLE);
      return;
    }

    // Adaptive polling mode
    var hero = null;
    for (var i = 0; i < snap.seats.length; i++) {
      if (snap.seats[i].is_hero) { hero = snap.seats[i]; break; }
    }
    var avail = hero ? hero.available_actions : [];

    // Reset cashout preselect on new hand (board resets to empty)
    var boardLen = snap.board.flop.length + (snap.board.turn ? 1 : 0) + (snap.board.river ? 1 : 0);
    if (boardLen === 0 && _lastBoardLen > 0) {
      if (_cashoutPre) console.log('[W4P] New hand — cashout preselect cleared');
      _cashoutPre = false;
      _preAction = null;
    }
    _lastBoardLen = boardLen;
    if (avail.length > 0) _mode = 'HERO_TURN';
    else if (snap.street !== 'PREFLOP') _mode = 'HAND_ACTIVE';
    else _mode = 'IDLE';

    // Send on state change OR heartbeat
    var hash = stateHash(snap);
    var now = Date.now();
    var changed = hash !== _lastHash;
    var heartbeat = (now - _lastSendTime) >= HEARTBEAT_MS;

    tryCashout();
    if (changed || heartbeat) {
      _lastHash = hash;
      _lastSendTime = now;
      sendSnapshot(snap);

      if (hero) {
        console.log('[W4P] #' + _n + (heartbeat && !changed ? ' (hb)' : '') +
                    ' ' + snap.street + ' pot=R' + snap.pot_zar +
                    ' ' + hero.name + '@seat' + hero.seat_index +
                    ' [' + hero.hole_cards.join(',') + ']' +
                    ' seats=' + snap.seats.length +
                    ' board=' + (snap.board.flop.join('') || '-'));
      }
    }

    // Fire pre-action if queued and actions available
    if (_preAction && avail.length > 0) {
      runPreAction(avail);
    }

    window._w4p_timer = setTimeout(tick, POLL_MS[_mode] || 1000);
  }

  // ── Start ────────────────────────────────────────────────────
  untickWaitBB();
  window._w4p_bbTimer = setInterval(untickWaitBB, 5000);

  console.log('[W4P] v16 autodetect | session=' + _sessionId);
  console.log('[W4P] Polling: hero=' + POLL_MS.HERO_TURN + 'ms cmd=' + CMD_MS.HERO_TURN + 'ms');
  console.log('[W4P] API: ' + API_BASE + ' | Remote: potlimitomaha.xyz/remote');
  tick();

  // ── Public API for debugging ─────────────────────────────────
  window._w4p_buildSnapshot = buildSnapshot;
  window._w4pClickAction = clickAction;
  window._w4pHandleCommand = handleCommand;
  window._w4pSelectMax = selectMax;
  window._w4pSelectMin = selectMin;
  window._w4pSelectPot = selectPot;
  window._w4pActions = getAvailableActions;
  window._w4p_detectButtons = detectButtons;
  window._w4p_getDetectedBtns = function() { return _detectedBtns; };
  window._w4p_injected = true;
  window._w4p_stop = function() {
    clearTimeout(window._w4p_timer);
    clearTimeout(window._w4p_cmdTimer);
    clearInterval(window._w4p_bbTimer);
    if (_cashoutTimer) clearInterval(_cashoutTimer);
    console.log('[W4P] stopped');
  };
})();
