/**
 * N4P Remote Control Script
 *
 * IMPORTANT: This script MUST run inside the poker iframe (poker-web.pokerbet.co.za),
 * NOT from the parent page. The poker client is cross-origin, so querySelector()
 * from parent will fail with "cross-origin" error.
 *
 * Injection method: Browser extension or userscript that runs in iframe context.
 */
var N4P = {
  POLL_MS: 250,
  CMD_POLL_MS: 250,
  API_BASE: 'https://test.potlimitomaha.xyz:8080/api',
  TRACKER_KEY: 'trk_default',
  _seatToken: sessionStorage.getItem('n4p_seat_token') || null,
  _preAction: null,
  _lastSampleKey: '',
  _commandTimer: null,
  _sessionId: 'sess-' + Date.now(),
  _executionLock: false,

  SELECTORS: {
    MAX_BUTTON: [
      'sg-poker-betting-slider > div > div.limits-buttons-v-p > ul > li:nth-child(4) > p',
      '.limits-buttons-v-p ul li:nth-child(4)',
      '.limits-buttons-v-p li:nth-child(4) p'
    ],
    CONFIRM_BUTTON: [
      'div.f-right-column-p > ul > li:nth-child(3) > div > p',
      '.f-right-column-p ul li:nth-child(3) div p',
      '.f-right-column-p li:nth-child(3)'
    ],
    FOLD_BUTTON: [
      '.f-right-column-p ul li:nth-child(5)',
      '.f-right-column-p li:nth-child(5)'
    ],
    CALL_BUTTON: [
      '.f-right-column-p ul li:nth-child(6)',
      '.f-right-column-p li:nth-child(6)'
    ],
    CHECK_BUTTON: [
      '.f-right-column-p ul li:nth-child(6)',
      '.f-right-column-p li:nth-child(6)'
    ],
    RAISE_INPUT: [
      '.f-right-column-p input[type="text"]',
      '.f-right-column-p input[type="number"]',
      'input[type="text"]',
      'input[type="number"]'
    ],
    MIN_BUTTON: [
      'sg-poker-betting-slider > div > div.limits-buttons-v-p > ul > li:nth-child(1) > p',
      '.limits-buttons-v-p ul li:nth-child(1)',
      '.limits-buttons-v-p li:nth-child(1) p'
    ],
    CASHOUT_BUTTON: [
      '[data-action="cashout"]',       // BEST: data attribute
      '#cashout-btn',                  // Stable ID
      'button[data-action="cashout"]', // Compound: type + data
      'button#cashout-btn',            // Compound: type + ID
      'button.cash_out-c',             // Compound: type + class
      '.control-b-view-p.cash_out-c',  // Compound: both classes
      '.cash_out-c',                   // Single class (less specific)
      '.control-b-view-p'              // Generic fallback (last resort)
    ]
  },

  buildSnapshot: function() {
    var containers = document.querySelectorAll('.player-mini-container-p');
    if (containers.length === 0) return null;

    var tableIdMatch = location.href.match(/tbl\/(\d+)/);
    var tableId = tableIdMatch ? tableIdMatch[1] : null;
    if (!tableId) return null;

    var seats = [];
    var heroSeat = null;
    var communityCards = [];

    // Community cards (outside any player container)
    var allCardEls = document.querySelectorAll('.single-cart-view-p');
    for (var i = 0; i < allCardEls.length; i++) {
      var el = allCardEls[i];
      if (!el.closest('.player-mini-container-p')) {
        var m = el.className.match(/icon-layer2_([shdc])(10|[akqjt2-9])_p-c-d/i);
        if (m) communityCards.push(m[1].toLowerCase() + m[2].toLowerCase());
      }
    }

    // Seats
    for (var i = 0; i < containers.length; i++) {
      var cont = containers[i];
      // Read selfPlayer from explicit DOM marker (NEVER infer from cards/buttons)
      var isHero = cont.classList.contains('self-player');
      var nameEl = cont.querySelector('p.single-win-item-sizes');
      var name = nameEl ? nameEl.textContent.trim() : null;
      var stackEl = cont.querySelector('.player-text-info-p span b');
      var stack = stackEl ? parseFloat(stackEl.textContent.replace(/[^0-9.]/g,'')) : 0;

      var hole = [];
      if (isHero) {
        var heroCardEls = cont.querySelectorAll('.single-cart-view-p');
        for (var j = 0; j < heroCardEls.length; j++) {
          var m2 = heroCardEls[j].className.match(/icon-layer2_([shdc])(10|[akqjt2-9])_p-c-d/i);
          if (m2) hole.push(m2[1].toLowerCase() + m2[2].toLowerCase());
        }
      }

      var status = cont.classList.contains('seat-out-v') ? 'sitting_out' : 'playing';
      var seatIndex = i;

      var seatObj = {
        seat_index: seatIndex,
        name: name,
        stack_zar: stack,
        hole_cards: hole,
        cards_count: hole.length,
        cards_visible: hole.length > 0,
        is_hero: isHero,
        is_dealer: false,
        status: status
      };
      seats.push(seatObj);
      if (isHero) heroSeat = seatObj;
    }

    // Dealer position
    var dealerMatch = document.querySelector('.dealer-icon-view');
    var dealerSeat = dealerMatch ? parseInt((dealerMatch.className.match(/position-(\d+)/) || [])[1]) : null;

    // Action buttons (using selector arrays)
    var foldBtn = this.findFirstVisible(this.SELECTORS.FOLD_BUTTON);
    var checkCallBtn = this.findFirstVisible(this.SELECTORS.CALL_BUTTON);
    var raiseBtn = this.findFirstVisible(this.SELECTORS.CONFIRM_BUTTON);
    var potEl = document.querySelector('.pot-w-view-p');
    var pot = potEl ? parseFloat(potEl.textContent.replace(/[^0-9.]/g,'')) : 0;

    // Scrape available actions with amounts
    var actions = [];

    if (foldBtn) {
      actions.push({action: 'fold', amount: 0});
    }

    if (checkCallBtn) {
      var btnText = checkCallBtn.textContent.toLowerCase();
      if (btnText.includes('check')) {
        actions.push({action: 'check', amount: 0});
      } else if (btnText.includes('call')) {
        var callAmt = parseFloat(btnText.replace(/[^0-9.]/g,'')) || 0;
        actions.push({action: 'call', amount: callAmt});
      }
    }

    // Raise control consists of TWO separate sections:
    // 1. INPUT field (editable numeric field)
    // 2. MAX button (separate clickable button that auto-fills max)
    var raiseInput = this.findFirstVisible(this.SELECTORS.RAISE_INPUT);
    var maxBtn = this.findFirstVisible(this.SELECTORS.MAX_BUTTON);
    var minBtn = this.findFirstVisible(this.SELECTORS.MIN_BUTTON);

    var raiseData = null;
    if (raiseInput) {
      var currentVal = parseFloat(raiseInput.value.replace(/[^0-9.]/g,'')) || 0;

      // Extract min/max from button labels (NOT from input attributes)
      var minVal = 0;
      var maxVal = heroSeat ? heroSeat.stack_zar : 0;

      if (minBtn && this.isVisible(minBtn)) {
        var minText = minBtn.textContent.replace(/[^0-9.]/g,'');
        if (minText) minVal = parseFloat(minText);
      }

      if (maxBtn && this.isVisible(maxBtn)) {
        var maxText = maxBtn.textContent.replace(/[^0-9.]/g,'');
        if (maxText) maxVal = parseFloat(maxText);
      }

      raiseData = {
        current: currentVal,
        min: minVal,
        max: maxVal,
        has_max_button: !!(maxBtn && this.isVisible(maxBtn))
      };

      if (raiseBtn && this.isVisible(raiseBtn)) {
        actions.push({
          action: 'raise',
          amount: currentVal,
          min: minVal,
          max: maxVal
        });
      }
    }

    var snap = {
      payload_id: 'snap-' + Date.now(),
      session_id: this._sessionId,
      machine_id: 'browser',
      client_id: 'tm_client',
      table_id: tableId,
      deal_id: communityCards.slice(0,3).join(''),
      timestamp_utc: new Date().toISOString(),
      variant: 'plo5-6max',
      street: communityCards.length >= 3 ? 'FLOP' : 'PREFLOP',
      table_size: seats.length,
      dealer_seat: dealerSeat,
      pot_zar: pot,
      seats: seats,
      board: { flop: communityCards.slice(0,3), turn: communityCards[3]||null, river: communityCards[4]||null },
      actions: actions,
      raise_input: raiseData,
      action_buttons: { visible: !!foldBtn||!!checkCallBtn, fold: !!foldBtn, check: !!checkCallBtn, call: !!checkCallBtn, call_amt: null },
      player_name: heroSeat ? heroSeat.name : '',
      stack_zar: heroSeat ? heroSeat.stack_zar : 0,
      hole_cards: heroSeat ? heroSeat.hole_cards : [],
      flop: communityCards.slice(0,3),
      turn: communityCards[3] || null,
      river: communityCards[4] || null
    };
    return snap;
  },

  isReady: function(snap) {
    if (!snap.hole_cards || snap.hole_cards.length < 4) return {ready: false};
    var key = snap.hole_cards.join('') + '/' + snap.flop.join('') + (snap.turn||'') + (snap.river||'');
    if (key === this._lastSampleKey) return {ready: false};
    return {ready: true, sampleKey: key};
  },

  sendSnapshot: function(snap) {
    if (!this._seatToken) {
      fetch(this.API_BASE + '/snapshot', {
        method: 'POST',
        headers: {'Content-Type':'application/json', 'X-API-Key': this.TRACKER_KEY},
        body: JSON.stringify(snap)
      })
        .then(r => r.json())
        .then(data => {
          if (data.ok && data.seat_token) {
            this._seatToken = data.seat_token;
            sessionStorage.setItem('n4p_seat_token', this._seatToken);
            this.startCommandPolling();
          }
        });
    } else {
      fetch(this.API_BASE + '/snapshot', {
        method: 'POST',
        headers: {'Content-Type':'application/json', 'X-API-Key': this.TRACKER_KEY},
        body: JSON.stringify(snap)
      });
    }
  },

  startCommandPolling: function() {
    if (this._commandTimer) return;
    this._commandTimer = setInterval(function() {
      fetch(this.API_BASE + '/commands/pending?token=' + this._seatToken)
        .then(r => r.json())
        .then(data => {
          if (data.ok && data.command) {
            this.handleCommand(data.command);
            fetch(this.API_BASE + '/commands/ack', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({token: this._seatToken, command_id: data.command.id})
            });
          }
        }.bind(this));
    }.bind(this), this.CMD_POLL_MS);
  },

  handleCommand: function(cmd) {
    console.log('[N4P] CMD RECEIVED → ' + cmd.type);
    switch (cmd.type) {
      case 'fold': this.executeNow('fold'); break;
      case 'check': this.executeNow('check'); break;
      case 'call': this.executeNow('call'); break;
      case 'raise': this.executeRaise(cmd.amount); break;
      case 'raise_max': this.executeRaiseMax(); break;
      case 'raise_pot': this.executeRaisePot(); break;
      case 'check_fold': this._preAction = 'check_fold'; break;
      case 'check_call': this._preAction = 'check_call'; break;
      case 'clear_preaction': this._preAction = null; break;
      case 'cashout': this.executeCashout(); break;
    }
  },

  executeNow: function(action) {
    this.withLock(function() {
      console.log('[N4P] Executing → ' + action.toUpperCase());

      var selectorMap = {
        fold: this.SELECTORS.FOLD_BUTTON,
        check: this.SELECTORS.CHECK_BUTTON,
        call: this.SELECTORS.CALL_BUTTON
      };

      var keywordMap = {
        fold: ['fold'],
        check: ['check'],
        call: ['call']
      };

      var selectors = selectorMap[action];
      var keywords = keywordMap[action];

      if (this.clickWithFallback(selectors, keywords)) {
        console.log('[N4P] ✓ EXECUTED → ' + action.toUpperCase());
      } else {
        console.log('[N4P] ✗ BUTTON NOT FOUND for ' + action.toUpperCase());
      }
    }.bind(this));
  },

  getRaiseInputValue: function() {
    var raiseInput = this.findFirstVisible(this.SELECTORS.RAISE_INPUT);
    return raiseInput ? raiseInput.value : '';
  },

  getRaiseInput: function() {
    return this.findFirstVisible(this.SELECTORS.RAISE_INPUT);
  },

  executeRaise: function(amount) {
    this.withLock(function() {
      console.log('[N4P] Executing RAISE → ' + amount);

      // Find raise input using selector array
      var raiseInput = this.getRaiseInput();
      if (!raiseInput) {
        console.log('[N4P] ✗ Raise input not found');
        return;
      }

      raiseInput.focus();
      raiseInput.value = '';
      raiseInput.value = amount;
      raiseInput.dispatchEvent(new Event('input', {bubbles: true}));
      raiseInput.dispatchEvent(new Event('change', {bubbles: true}));
      console.log('[N4P] ✓ Set raise amount to ' + amount);

      setTimeout(function() {
        // Find confirm button using selector array + text fallback
        if (this.clickWithFallback(this.SELECTORS.CONFIRM_BUTTON, ['raise', 'bet', 'all in'])) {
          console.log('[N4P] ✓ RAISE EXECUTED');
        } else {
          console.log('[N4P] ✗ RAISE confirm button not found');
        }
      }.bind(this), 150);
    }.bind(this));
  },

  executeRaiseMax: function() {
    this.withLock(function() {
      console.log('[N4P] Executing RAISE MAX (composite action)');

      // Step 1: Find MAX button using selector array + text fallback
      var maxBtn = this.findFirstClickable(this.SELECTORS.MAX_BUTTON);
      if (!maxBtn) {
        maxBtn = this.findButtonByText(['max']);
        if (maxBtn && this.isClickable(maxBtn)) {
          console.log('[N4P] ✓ Found MAX button via text');
        }
      }

      if (!maxBtn) {
        console.log('[N4P] ✗ MAX button not found');
        return;
      }

      // Step 2: Get initial input value
      var beforeValue = this.getRaiseInputValue();
      if (!beforeValue || beforeValue === '0' || beforeValue === '') {
        console.log('[N4P] ⚠ Raise input empty before MAX click');
      }

      // Step 3: Click MAX button
      maxBtn.click();
      console.log('[N4P] ✓ Clicked MAX button');

      // Step 4: Wait 200ms and verify value changed, then click confirm
      setTimeout(function() {
        var afterValue = this.getRaiseInputValue();

        if (!afterValue || afterValue === beforeValue || afterValue === '0' || afterValue === '') {
          console.log('[N4P] ✗ MAX click did not change raise input (before: ' + beforeValue + ', after: ' + afterValue + ')');
          return;
        }
        console.log('[N4P] ✓ Input value changed: ' + beforeValue + ' → ' + afterValue);

        // Step 5: Click CONFIRM button using selector array + text fallback
        if (this.clickWithFallback(this.SELECTORS.CONFIRM_BUTTON, ['raise', 'bet', 'all in'])) {
          console.log('[N4P] ✓ RAISE MAX EXECUTED');
        } else {
          console.log('[N4P] ✗ RAISE confirm button not found');
        }
      }.bind(this), 200);
    }.bind(this));
  },

  executeRaisePot: function() {
    console.log('[N4P] Executing RAISE POT');
    var potBtn = document.querySelector('.f-right-column-p ul li:nth-child(3)');
    if (potBtn && this.isVisible(potBtn)) {
      potBtn.click();
      console.log('[N4P] ✓ Clicked POT amount (115%)');
      setTimeout(function() {
        var raiseBtn = document.querySelector('.f-right-column-p ul li:nth-child(7)');
        if (raiseBtn && this.isVisible(raiseBtn)) {
          raiseBtn.click();
          console.log('[N4P] ✓ Clicked RAISE confirm → RAISE POT EXECUTED');
        }
      }.bind(this), 150);
    } else {
      console.log('[N4P] ✗ POT button not visible');
    }
  },

  executeCashout: function() {
    this.withLock(function() {
      console.log('[N4P] Executing CASHOUT');

      // Try selector array first
      var cashoutBtn = this.findFirstClickable(this.SELECTORS.CASHOUT_BUTTON);

      // Fallback: text search in buttons
      if (!cashoutBtn) {
        var allButtons = document.querySelectorAll('button, .control-b-view-p');
        for (var i = 0; i < allButtons.length; i++) {
          var btn = allButtons[i];
          if (!this.isClickable(btn)) continue;
          var text = btn.textContent.toLowerCase();
          if (text.includes('cash') && !text.includes('cashier')) {
            cashoutBtn = btn;
            console.log('[N4P] ✓ Found CASHOUT via text search');
            break;
          }
        }
      }

      if (cashoutBtn) {
        cashoutBtn.click();
        console.log('[N4P] ✓ CASHOUT EXECUTED');
      } else {
        console.log('[N4P] ✗ CASHOUT button not found');
      }
    }.bind(this));
  },

  isVisible: function(el) {
    if (!el) return false;
    var style = window.getComputedStyle(el);
    return style.display !== 'none' &&
           style.visibility !== 'hidden' &&
           style.opacity !== '0' &&
           el.offsetParent !== null;
  },

  isClickable: function(el) {
    if (!el) return false;
    if (!this.isVisible(el)) return false;
    if (el.disabled) return false;
    var style = window.getComputedStyle(el);
    if (style.pointerEvents === 'none') return false;
    return true;
  },

  findFirstVisible: function(selectors) {
    for (var i = 0; i < selectors.length; i++) {
      var el = document.querySelector(selectors[i]);
      if (el && this.isVisible(el)) {
        console.log('[N4P] ✓ Matched selector [' + i + ']: ' + selectors[i]);
        return el;
      }
    }
    return null;
  },

  findFirstClickable: function(selectors) {
    for (var i = 0; i < selectors.length; i++) {
      var el = document.querySelector(selectors[i]);
      if (this.isClickable(el)) {
        console.log('[N4P] ✓ Matched clickable selector [' + i + ']: ' + selectors[i]);
        return el;
      }
    }
    return null;
  },

  clickWithFallback: function(selectors, keywords) {
    // Try CSS selectors first
    var el = this.findFirstClickable(selectors);
    if (el) {
      el.click();
      return true;
    }
    // Try text match fallback
    if (keywords && keywords.length > 0) {
      el = this.findButtonByText(keywords);
      if (el && this.isClickable(el)) {
        console.log('[N4P] ✓ Matched via text: ' + keywords.join('/'));
        el.click();
        return true;
      }
    }
    return false;
  },

  withLock: function(action) {
    if (this._executionLock) {
      console.log('[N4P] ✗ Execution locked (action in progress)');
      return;
    }
    this._executionLock = true;
    try {
      action();
    } finally {
      setTimeout(function() {
        this._executionLock = false;
      }.bind(this), 500);
    }
  },

  findButtonByText: function(keywords) {
    var buttons = document.querySelectorAll('button, .control-b-view-p, li > p, li > div > p');
    for (var i = 0; i < buttons.length; i++) {
      var btn = buttons[i];
      if (!this.isVisible(btn)) continue;
      var text = btn.textContent.toLowerCase().trim();
      for (var j = 0; j < keywords.length; j++) {
        if (text.includes(keywords[j].toLowerCase())) {
          return btn;
        }
      }
    }
    return null;
  },

  injectManualControls: function() {
    // Only create if doesn't exist
    if (document.getElementById('n4p-manual-controls')) return;

    console.log('[N4P] Manual control buttons injected');

    // Create container
    var container = document.createElement('div');
    container.id = 'n4p-manual-controls';
    container.style.cssText = 'position:fixed;top:10px;right:10px;z-index:99999;display:flex;gap:5px;pointer-events:none;';

    // FOLD button
    var foldBtn = document.createElement('button');
    foldBtn.textContent = 'FOLD';
    foldBtn.style.cssText = 'padding:6px 10px;background:rgba(244,67,54,0.8);color:white;border:none;border-radius:4px;cursor:pointer;font-weight:bold;font-size:11px;box-shadow:0 2px 4px rgba(0,0,0,0.3);';
    foldBtn.style.pointerEvents = 'auto';
    foldBtn.onclick = function() {
      console.log('[N4P] Manual FOLD clicked');
      N4P.executeNow('fold');
    };

    // CALL button
    var callBtn = document.createElement('button');
    callBtn.textContent = 'CALL';
    callBtn.style.cssText = 'padding:6px 10px;background:rgba(33,150,243,0.8);color:white;border:none;border-radius:4px;cursor:pointer;font-weight:bold;font-size:11px;box-shadow:0 2px 4px rgba(0,0,0,0.3);';
    callBtn.style.pointerEvents = 'auto';
    callBtn.onclick = function() {
      console.log('[N4P] Manual CALL clicked');
      N4P.executeNow('call');
    };

    // MAX button
    var maxBtn = document.createElement('button');
    maxBtn.textContent = 'MAX';
    maxBtn.style.cssText = 'padding:6px 10px;background:rgba(255,100,0,0.8);color:white;border:none;border-radius:4px;cursor:pointer;font-weight:bold;font-size:11px;box-shadow:0 2px 4px rgba(0,0,0,0.3);';
    maxBtn.style.pointerEvents = 'auto';
    maxBtn.onclick = function() {
      console.log('[N4P] Manual MAX clicked');
      N4P.executeRaiseMax();
    };

    // CASHOUT button
    var cashoutBtn = document.createElement('button');
    cashoutBtn.textContent = 'CASHOUT';
    cashoutBtn.style.cssText = 'padding:6px 10px;background:rgba(255,193,7,0.8);color:#000;border:none;border-radius:4px;cursor:pointer;font-weight:bold;font-size:11px;box-shadow:0 2px 4px rgba(0,0,0,0.3);';
    cashoutBtn.style.pointerEvents = 'auto';
    cashoutBtn.onclick = function() {
      console.log('[N4P] Manual CASHOUT clicked');
      N4P.executeCashout();
    };

    container.appendChild(foldBtn);
    container.appendChild(callBtn);
    container.appendChild(maxBtn);
    container.appendChild(cashoutBtn);

    document.body.appendChild(container);
  },

  checkPreAction: function() {
    if (!this._preAction) return;
    var foldBtn = document.querySelector('.f-right-column-p ul li:nth-child(5)');
    var checkCallBtn = document.querySelector('.f-right-column-p ul li:nth-child(6)');

    if (this._preAction === 'check_fold') {
      if (checkCallBtn && this.isVisible(checkCallBtn)) {
        var text = checkCallBtn.textContent.toLowerCase();
        if (text.includes('check')) this.executeNow('check');
        else if (foldBtn && this.isVisible(foldBtn)) this.executeNow('fold');
      }
    } else if (this._preAction === 'check_call') {
      if (checkCallBtn && this.isVisible(checkCallBtn)) this.executeNow('call');
    }
  }
};

(function main() {
  console.log('%c[N4P] Remote table control v1.0 loaded — run on pokerbet.co.za', 'color:#00d4aa;font-weight:bold');

  // Inject manual control buttons (fallback/debug)
  N4P.injectManualControls();

  setInterval(function() {
    var snap = N4P.buildSnapshot();
    if (!snap) return;

    var gate = N4P.isReady(snap);
    if (gate.ready) {
      N4P.sendSnapshot(snap);
      N4P._lastSampleKey = gate.sampleKey;
    }

    N4P.checkPreAction();
  }, N4P.POLL_MS);
})();
