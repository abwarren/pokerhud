// CB2K — Cyber Basketball 2K26 Sportsbook Scraper + Bet Executor
// Injects into PokerBet sportsbook pages (BetConstruct/SpringBME DOM)
// v3.0: Calibrated to actual PokerBet DOM classes (2026-04-24)

(function(){
  'use strict';

  // ── Cleanup prior instances ──────────────────────────────────
  if (window._cb2k_timer) { clearTimeout(window._cb2k_timer); window._cb2k_timer = null; }
  if (window._cb2k_cmdTimer) { clearTimeout(window._cb2k_cmdTimer); window._cb2k_cmdTimer = null; }
  if (window._cb2k) { clearInterval(window._cb2k); window._cb2k = null; }
  window._cb2k_injected = false;

  // ── Config ───────────────────────────────────────────────────
  var API_BASE = 'https://potlimitomaha.xyz/blm/api/hud/cyber/markets';
  var POLL_MS = { MARKETS_VISIBLE: 1500, NO_MARKETS: 4000 };
  var CMD_POLL_MS = 500;
  var HEARTBEAT_MS = 5000;

  var _mode = 'NO_MARKETS';
  var _lastHash = null;
  var _lastSendTime = 0;
  var _n = 0;
  var _bootTicks = 0;
  var _sessionId = 'cb2k_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
  var _executedCmds = {};

  // ══════════════════════════════════════════════════════════════
  //  ACTUAL POKERBET SELECTORS (calibrated 2026-04-24)
  // ══════════════════════════════════════════════════════════════

  // ── Event-view page (single game, all markets) ───────────────
  var EV = {
    container:      '.game-details-container-bc, .game-details-container-live-bc',
    teamName:       '.game-d-c-b-r-c-team-name-bc',
    scoreItem:      '.game-d-c-b-r-c-score-item-bc',
    scoreCount:     '.game-details-c-body-count-bc',
    clock:          '.game-details-c-head-time-bc',
    period:         '.game-details-additional-info-title-bc',
    setScore:       '.set-score-bc',
    sportLeague:    '.game-d-c-h-c-r-sport-league-bc',
    // Market groups
    marketGroupHead:  '.sgm-market-g-head-bc',
    marketGroupTitle: '.sgm-market-g-h-title-bc',
    marketGroupBody:  '.sgm-market-g-item-bc',
    marketGroupHolder:'.market-group-holder-bc',
    marketGroupItem:  '.market-group-item-bc',
    marketCell:       '.sgm-market-g-i-cell-bc',
    // Individual market (clickable selection)
    market:         '.market-bc',
    marketName:     '.market-name-bc',
    marketCoeff:    '.market-coefficient-bc',
    marketOdd:      '.market-odd-bc',
  };

  // ── Live list page (multiple games, inline markets) ──────────
  var LV = {
    competition:    '.competition-wrapper-bc',
    compTitle:      '.competition-title-bc',
    gameRow:        '.hm-row-bc',
    // Sidebar sport lists
    subList:        '.sp-sub-list-bc',
    subListHead:    '.sp-s-l-head-bc',
    subListTitle:   '.sp-s-l-h-title-bc',
    subListContent: '.sp-s-l-b-content-bc',
  };

  // ── Betslip ──────────────────────────────────────────────────
  var BS = {
    betslip:    '.betslip-bc',
    body:       '.bs-f-body-bc, .bs-f-b-content-bc',
    stakeInput: '.betslip-bc input[type="number"], .betslip-bc input[type="text"], .bs-f-b-content-bc input',
    confirmBtn: '.betslip-bc button[class*="place-bet"], .betslip-bc button[class*="accept"], .bs-f-body-bc button',
    error:      '.betslip-bc [class*="error"]',
    success:    '.betslip-bc [class*="success"], .betslip-bc [class*="accepted"]',
    close:      '.betslip-bc [class*="close"], .betslip-bc [class*="remove"]',
  };

  // ── Helpers ──────────────────────────────────────────────────
  function log(msg) { console.log('%c[CB2K] ' + msg, 'color: #00bcd4; font-weight: bold;'); }
  function warn(msg) { console.warn('[CB2K] ' + msg); }

  function qs(el, sel) {
    try { return el.querySelector(sel); } catch(e) { return null; }
  }

  function qsa(el, sel) {
    try { return el.querySelectorAll(sel); } catch(e) { return []; }
  }

  function getText(el) {
    return el ? (el.textContent || el.innerText || '').trim() : '';
  }

  function getNum(text) {
    var n = parseFloat((text || '').replace(/[^\d.\-]/g, ''));
    return isNaN(n) ? null : n;
  }

  function simpleHash(str) {
    var hash = 0;
    for (var i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    return hash.toString(36);
  }

  // Parse URL for game context
  function parseUrl() {
    var path = location.pathname;
    var parts = path.split('/');
    var info = { gameId: null, competition: '', homeTeam: '', awayTeam: '', isEventView: false };

    if (path.indexOf('/event-view/') !== -1) {
      info.isEventView = true;
      // URL: .../event-view/Basketball/World/18295203/cyber-basketball-2k26-matches/29585425/team1-team2
      for (var i = 0; i < parts.length; i++) {
        if (/^\d{5,}$/.test(parts[i])) {
          if (!info.competition && parts[i - 1]) info.competition = parts[i - 1];
          info.gameId = parts[i];
        }
      }
      var lastPart = parts[parts.length - 1] || '';
      if (lastPart.indexOf('-cyber-') !== -1 || lastPart.indexOf('-vs-') !== -1) {
        // "denver-nuggets-cyber-houston-rockets-cyber"
        // Split at the pattern where teams divide
        var teamStr = lastPart.replace(/-cyber-/g, '-cyber|').split('|');
        if (teamStr.length >= 2) {
          info.homeTeam = teamStr[0].replace(/-/g, ' ').trim();
          info.awayTeam = teamStr[1].replace(/-/g, ' ').trim();
        }
      }
    }
    return info;
  }


  // ══════════════════════════════════════════════════════════════
  //  EVENT-VIEW SCRAPER (single game page, all markets visible)
  // ══════════════════════════════════════════════════════════════
  function scrapeEventView() {
    var markets = [];
    var container = qs(document, EV.container);
    if (!container) return markets;

    // Team names
    var teamEls = qsa(document, EV.teamName);
    var homeName = teamEls.length >= 1 ? getText(teamEls[0]) : '';
    var awayName = teamEls.length >= 2 ? getText(teamEls[1]) : '';

    // Fall back to URL if DOM doesn't have team names
    if (!homeName) {
      var urlInfo = parseUrl();
      homeName = urlInfo.homeTeam;
      awayName = urlInfo.awayTeam;
    }

    // Scores — game-d-c-b-r-c-score-item-bc appears 9 times
    // Typically: [total_home, q1h, q2h, q3h, ..., total_away, q1a, ...]
    // Or: [home_total, away_total] followed by quarter scores
    var scoreEls = qsa(document, EV.scoreItem);
    var scoreH = null, scoreA = null;

    // Try to get main score from game-details-c-body-count-bc
    var countEl = qs(document, EV.scoreCount);
    if (countEl) {
      var countText = getText(countEl);
      var scoreParts = countText.split(/[-:]/);
      if (scoreParts.length === 2) {
        scoreH = parseFloat(scoreParts[0].trim());
        scoreA = parseFloat(scoreParts[1].trim());
      }
    }

    // Fallback: first score items
    if (scoreH === null && scoreEls.length >= 2) {
      scoreH = getNum(getText(scoreEls[0]));
      scoreA = getNum(getText(scoreEls[1]));
    }

    // Clock & Period
    var clockEls = qsa(document, EV.clock);
    var clockText = clockEls.length > 0 ? getText(clockEls[0]) : '';
    var periodEl = qs(document, EV.period);
    var periodText = periodEl ? getText(periodEl) : '';
    if (!periodText) {
      var setScoreEl = qs(document, EV.setScore);
      if (setScoreEl) periodText = getText(setScoreEl);
    }

    // League info
    var leagueEl = qs(document, EV.sportLeague);
    var leagueText = leagueEl ? getText(leagueEl) : '';

    // Game ID from URL
    var urlInfo = parseUrl();
    var gameId = urlInfo.gameId || ('cb2k_' + simpleHash(homeName + awayName));

    // ── Find Total (Over/Under) market group ────────────────
    var groupHeads = qsa(document, EV.marketGroupHead);
    for (var gh = 0; gh < groupHeads.length; gh++) {
      var headEl = groupHeads[gh];
      var titleEl = qs(headEl, EV.marketGroupTitle);
      var title = getText(titleEl).toLowerCase();

      // Match "Total", "Match Total", "Game Total"
      if (title.indexOf('total') === -1) continue;

      // Find the market group body — it's the next sibling element
      var bodyEl = headEl.nextElementSibling;
      if (!bodyEl) continue;

      // Also check: the body might be a child of the same parent
      var parentGroup = headEl.parentElement;
      if (!bodyEl.querySelector || !qs(bodyEl, EV.market)) {
        // Try finding body within parent
        bodyEl = qs(parentGroup, EV.marketGroupBody) || qs(parentGroup, EV.marketGroupHolder);
        if (!bodyEl) continue;
      }

      // Find all market selections within this group
      var marketEls = qsa(bodyEl, EV.market);
      var overPrice = null, underPrice = null, overBtn = null, underBtn = null;
      var line = null;

      for (var mi = 0; mi < marketEls.length; mi++) {
        var mkt = marketEls[mi];
        var nameEl = qs(mkt, EV.marketName);
        var oddEl = qs(mkt, EV.marketOdd);
        var name = getText(nameEl).toLowerCase();
        var price = getNum(getText(oddEl));

        // Parse line from market name: "Over 228.5" or "Under 228.5"
        var lineMatch = name.match(/(\d+\.?\d*)/);
        if (lineMatch && !line) {
          var parsed = parseFloat(lineMatch[1]);
          if (parsed > 20) line = parsed;  // Basketball totals are always > 20
        }

        if (name.indexOf('over') !== -1 || name.indexOf('ov') !== -1) {
          overPrice = price;
          overBtn = mkt;  // The .market-bc element is the click target
        } else if (name.indexOf('under') !== -1 || name.indexOf('un') !== -1) {
          underPrice = price;
          underBtn = mkt;
        }
      }

      // Also try extracting line from group title: "Total 228.5"
      if (!line) {
        var titleLineMatch = title.match(/(\d+\.?\d*)/);
        if (titleLineMatch) {
          var tl = parseFloat(titleLineMatch[1]);
          if (tl > 20) line = tl;
        }
      }

      // If we found at least one price, build the market object
      if (overPrice || underPrice) {
        // Distinguish full-game Total from quarter Totals
        var isFullGame = title === 'total' || title === 'match total' ||
                         title === 'game total' || title.indexOf('total') !== -1 && title.indexOf('quarter') === -1 &&
                         title.indexOf('half') === -1 && title.indexOf('1st') === -1 &&
                         title.indexOf('2nd') === -1 && title.indexOf('3rd') === -1 &&
                         title.indexOf('4th') === -1;

        markets.push({
          game_id: gameId,
          home_team: homeName,
          away_team: awayName,
          home_score: scoreH,
          away_score: scoreA,
          total_score: (scoreH || 0) + (scoreA || 0),
          period: periodText,
          clock: clockText,
          line: line,
          over_price: overPrice,
          under_price: underPrice,
          market_id: null,
          over_event_id: null,
          under_event_id: null,
          over_selector: overBtn ? buildPath(overBtn) : null,
          under_selector: underBtn ? buildPath(underBtn) : null,
          competition: leagueText || urlInfo.competition || '',
          market_title: getText(titleEl),
          is_full_game: isFullGame,
          source: 'event_view',
        });
      }
    }

    return markets;
  }


  // ══════════════════════════════════════════════════════════════
  //  LIST-VIEW SCRAPER (live page with multiple games)
  // ══════════════════════════════════════════════════════════════
  function scrapeListView() {
    var markets = [];

    // Strategy A: Find competition wrappers with game rows
    var compEls = qsa(document, LV.competition);
    for (var ci = 0; ci < compEls.length; ci++) {
      var comp = compEls[ci];
      var compTitle = getText(qs(comp, LV.compTitle)).toLowerCase();

      // Filter for cyber basketball
      if (compTitle.indexOf('cyber') === -1 && compTitle.indexOf('2k') === -1 &&
          compTitle.indexOf('virtual') === -1 && compTitle.indexOf('esport') === -1) continue;

      var rows = qsa(comp, LV.gameRow);
      for (var ri = 0; ri < rows.length; ri++) {
        var m = scrapeListRow(rows[ri], compTitle);
        if (m) markets.push(m);
      }
    }

    // Strategy B: Find game rows directly (if no competition wrapper)
    if (markets.length === 0) {
      var allRows = qsa(document, LV.gameRow);
      for (var ri2 = 0; ri2 < allRows.length; ri2++) {
        var m2 = scrapeListRow(allRows[ri2], '');
        if (m2) markets.push(m2);
      }
    }

    return markets;
  }

  function scrapeListRow(row, compName) {
    // On list pages, each row has teams, scores, and inline market columns
    // Market columns use same classes: .market-bc, .market-odd-bc, .market-name-bc
    var teamEls = qsa(row, EV.teamName + ', [class*="team-name"]');
    var homeName = teamEls.length >= 1 ? getText(teamEls[0]) : '';
    var awayName = teamEls.length >= 2 ? getText(teamEls[1]) : '';
    if (!homeName) return null;

    // Scores
    var scoreEls = qsa(row, EV.scoreItem + ', [class*="score"]');
    var scoreH = scoreEls.length >= 1 ? getNum(getText(scoreEls[0])) : null;
    var scoreA = scoreEls.length >= 2 ? getNum(getText(scoreEls[1])) : null;

    // Clock
    var clockEl = qs(row, EV.clock + ', [class*="timer"], [class*="game-time"]');
    var clockText = clockEl ? getText(clockEl) : '';

    // Find over/under markets in the row
    var marketCells = qsa(row, EV.market);
    var overPrice = null, underPrice = null, line = null;
    var overBtn = null, underBtn = null;

    for (var i = 0; i < marketCells.length; i++) {
      var mkt = marketCells[i];
      var nameEl = qs(mkt, EV.marketName);
      var oddEl = qs(mkt, EV.marketOdd);
      var name = getText(nameEl).toLowerCase();
      var price = getNum(getText(oddEl));

      var lineMatch = name.match(/(\d+\.?\d*)/);
      if (lineMatch && !line) {
        var pl = parseFloat(lineMatch[1]);
        if (pl > 20) line = pl;
      }

      if (name.indexOf('over') !== -1) {
        overPrice = price; overBtn = mkt;
      } else if (name.indexOf('under') !== -1) {
        underPrice = price; underBtn = mkt;
      }
    }

    if (!overPrice && !underPrice) return null;

    return {
      game_id: 'cb2k_' + simpleHash(homeName + awayName),
      home_team: homeName,
      away_team: awayName,
      home_score: scoreH,
      away_score: scoreA,
      total_score: (scoreH || 0) + (scoreA || 0),
      period: '',
      clock: clockText,
      line: line,
      over_price: overPrice,
      under_price: underPrice,
      market_id: null,
      over_event_id: null,
      under_event_id: null,
      over_selector: overBtn ? buildPath(overBtn) : null,
      under_selector: underBtn ? buildPath(underBtn) : null,
      competition: compName || '',
      is_full_game: true,
      source: 'list_view',
    };
  }


  // ══════════════════════════════════════════════════════════════
  //  COMBINED SCRAPER
  // ══════════════════════════════════════════════════════════════
  function scrapeMarkets() {
    var markets = [];

    // Detect page type
    var isEventView = location.pathname.indexOf('/event-view/') !== -1 ||
                      qs(document, EV.container) !== null;

    if (isEventView) {
      markets = scrapeEventView();
    }

    // Also try list view (pages may have both)
    if (markets.length === 0) {
      markets = scrapeListView();
    }

    // Text-scan fallback: find Over/Under by walking text nodes
    if (markets.length === 0) {
      markets = textFallbackScrape();
    }

    return markets;
  }


  // ══════════════════════════════════════════════════════════════
  //  TEXT FALLBACK SCRAPER (last resort, DOM-agnostic)
  // ══════════════════════════════════════════════════════════════
  function textFallbackScrape() {
    var markets = [];
    var overEls = [];
    var underEls = [];

    // Find Over/Under text nodes
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
    var node;
    while (node = walker.nextNode()) {
      var t = node.textContent.trim().toLowerCase();
      if (/^over\b/.test(t)) overEls.push(node.parentElement);
      if (/^under\b/.test(t)) underEls.push(node.parentElement);
    }

    if (overEls.length === 0 || underEls.length === 0) return markets;

    // Pair over/under elements sharing a close ancestor
    for (var i = 0; i < overEls.length; i++) {
      for (var j = 0; j < underEls.length; j++) {
        var ancestor = commonAncestor(overEls[i], underEls[j], 8);
        if (!ancestor) continue;

        // Find odds near each
        var overOdd = findNearbyOdd(overEls[i]);
        var underOdd = findNearbyOdd(underEls[j]);

        // Find line (number > 20)
        var line = findLine(ancestor);

        // Get team names from page
        var teamEls = qsa(document, EV.teamName);
        var homeName = teamEls.length >= 1 ? getText(teamEls[0]) : '';
        var awayName = teamEls.length >= 2 ? getText(teamEls[1]) : '';

        if (overOdd || underOdd) {
          var urlInfo = parseUrl();
          markets.push({
            game_id: urlInfo.gameId || ('cb2k_' + simpleHash(homeName + awayName)),
            home_team: homeName || urlInfo.homeTeam,
            away_team: awayName || urlInfo.awayTeam,
            home_score: null, away_score: null, total_score: 0,
            period: '', clock: '',
            line: line,
            over_price: overOdd,
            under_price: underOdd,
            market_id: null, over_event_id: null, under_event_id: null,
            over_selector: overEls[i] ? buildPath(findClickable(overEls[i])) : null,
            under_selector: underEls[j] ? buildPath(findClickable(underEls[j])) : null,
            competition: urlInfo.competition || '',
            is_full_game: true,
            source: 'text_fallback',
          });
          return markets; // one pair is enough for fallback
        }
      }
    }
    return markets;
  }

  function commonAncestor(a, b, maxLevels) {
    var ancestors = [];
    var cur = a;
    for (var i = 0; i < maxLevels && cur; i++) { ancestors.push(cur); cur = cur.parentElement; }
    cur = b;
    for (var j = 0; j < maxLevels && cur; j++) {
      if (ancestors.indexOf(cur) !== -1) return cur;
      cur = cur.parentElement;
    }
    return null;
  }

  function findNearbyOdd(el) {
    // Check sibling elements for odds-like values (1.01 - 50.00)
    var parent = el ? el.parentElement : null;
    if (!parent) return null;
    var children = parent.querySelectorAll('*');
    for (var i = 0; i < children.length; i++) {
      var t = getText(children[i]).trim();
      if (/^\d{1,2}\.\d{1,2}$/.test(t)) {
        var v = parseFloat(t);
        if (v >= 1.01 && v <= 50) return v;
      }
    }
    // Check grandparent
    var gp = parent.parentElement;
    if (gp) {
      children = gp.querySelectorAll('*');
      for (var j = 0; j < children.length; j++) {
        var t2 = getText(children[j]).trim();
        if (/^\d{1,2}\.\d{1,2}$/.test(t2)) {
          var v2 = parseFloat(t2);
          if (v2 >= 1.01 && v2 <= 50) return v2;
        }
      }
    }
    return null;
  }

  function findLine(ancestor) {
    var els = ancestor.querySelectorAll('*');
    for (var i = 0; i < els.length; i++) {
      var t = getText(els[i]).trim();
      var n = parseFloat(t);
      if (!isNaN(n) && n > 20 && n < 500 && /^\d+\.?\d*$/.test(t)) return n;
    }
    return null;
  }

  function findClickable(el) {
    var cur = el;
    for (var i = 0; i < 5 && cur; i++) {
      if (cur.tagName === 'BUTTON' || cur.tagName === 'A') return cur;
      var cls = (cur.className || '').toLowerCase();
      if (cls.indexOf('market-bc') !== -1 || cls.indexOf('odd') !== -1 || cls.indexOf('coefficient') !== -1) return cur;
      cur = cur.parentElement;
    }
    return el;
  }


  // ── Build selector path for re-finding an element ────────────
  function buildPath(el) {
    if (!el) return null;
    // Try class-based path first (more stable than nth-child)
    var parts = [];
    var cur = el;
    while (cur && cur !== document.body && parts.length < 6) {
      var seg = cur.tagName.toLowerCase();
      // Prefer -bc classes for identification
      var bcClass = (cur.className || '').split(/\s+/).find(function(c) { return c.indexOf('-bc') !== -1; });
      if (bcClass) {
        seg = '.' + bcClass;
        // Add nth-of-type if there are siblings with same class
        var sibs = cur.parentElement ? cur.parentElement.querySelectorAll(':scope > .' + bcClass) : [];
        if (sibs.length > 1) {
          var idx = Array.prototype.indexOf.call(sibs, cur);
          if (idx >= 0) seg += ':nth-of-type(' + (idx + 1) + ')';
        }
      } else {
        var idx2 = 1;
        var sib = cur.previousElementSibling;
        while (sib) { idx2++; sib = sib.previousElementSibling; }
        seg += ':nth-child(' + idx2 + ')';
      }
      parts.unshift(seg);
      if (cur.id) { parts = ['#' + cur.id]; break; }
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  }


  // ── State hash for dedup ─────────────────────────────────────
  function marketHash(markets) {
    return simpleHash(markets.map(function(m) {
      return m.game_id + '|' + m.home_score + '|' + m.away_score + '|' +
             m.line + '|' + m.over_price + '|' + m.under_price + '|' + m.clock;
    }).join(';;'));
  }


  // ── Send snapshot to backend ─────────────────────────────────
  function sendSnapshot(markets) {
    var hash = marketHash(markets);
    var now = Date.now();
    if (hash === _lastHash && (now - _lastSendTime) < HEARTBEAT_MS) return;

    _lastHash = hash;
    _lastSendTime = now;
    _n++;

    var payload = {
      markets: markets,
      ts: now,
      url: location.href,
      page_title: document.title,
      session_id: _sessionId,
      n: _n,
    };

    fetch(API_BASE + '/snapshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(function(r) { return r.json(); })
      .then(function(d) {
        if (_n <= 5 || _n % 20 === 0) log('Snapshot #' + _n + ': ' + markets.length + ' markets sent');
      })
      .catch(function(e) {
        if (_n <= 5) warn('Send failed: ' + e.message);
      });
  }


  // ── Command polling ──────────────────────────────────────────
  function pollCommands() {
    fetch(API_BASE + '/commands')
      .then(function(r) { return r.json(); })
      .then(function(d) {
        var cmds = d.commands || [];
        for (var i = 0; i < cmds.length; i++) {
          var cmd = cmds[i];
          if (_executedCmds[cmd.id]) continue;
          _executedCmds[cmd.id] = true;
          log('Executing command #' + cmd.id + ': ' + cmd.type + ' on ' + cmd.game_id);
          executeBet(cmd);
        }
      })
      .catch(function(){})
      .finally(function() {
        window._cb2k_cmdTimer = setTimeout(pollCommands, CMD_POLL_MS);
      });
  }


  // ── Bet execution ────────────────────────────────────────────
  function executeBet(cmd) {
    var direction = cmd.direction || (cmd.type === 'click_under' ? 'under' : 'over');
    var targetBtn = null;

    // Strategy 1: Use stored selector path
    var selPath = direction === 'under' ? cmd.selector_under : cmd.selector_over;
    if (!selPath) selPath = cmd.selector;
    if (selPath) {
      try { targetBtn = document.querySelector(selPath); } catch(e) {}
    }

    // Strategy 2: Re-scrape and find by game + direction
    var markets;
    if (!targetBtn) {
      markets = scrapeMarkets();
      for (var i = 0; i < markets.length; i++) {
        var m = markets[i];
        // Match by game_id or team name
        var matchId = m.game_id === cmd.game_id;
        if (!matchId && cmd.game_id && m.game_id) {
          var n1 = cmd.game_id.replace(/\D+/g, '');
          var n2 = m.game_id.replace(/\D+/g, '');
          if (n1 && n2 && n1 === n2) matchId = true;
        }
        var matchTeam = cmd.home_team && m.home_team &&
                        m.home_team.toLowerCase().indexOf(cmd.home_team.toLowerCase().substring(0, 8)) !== -1;

        if (matchId || matchTeam) {
          var path = direction === 'under' ? m.under_selector : m.over_selector;
          if (path) {
            try { targetBtn = document.querySelector(path); } catch(e) {}
          }
          break;
        }
      }
    }

    if (!targetBtn) {
      var mIds = markets ? markets.map(function(m){ return m.game_id; }).join(', ') : 'none';
      warn('Button not found: ' + direction + ' for ' + cmd.game_id + ' | Available: [' + mIds + ']');
      ackCommand(cmd.id, false, 'Button not found');
      return;
    }

    // Click the .market-bc element (or its .market-coefficient-bc child)
    targetBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(function() {
      // Click the coefficient area specifically (Angular binds there)
      var clickTarget = qs(targetBtn, EV.marketCoeff) || targetBtn;
      clickTarget.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      log('Clicked ' + direction + ' button');

      // Wait for betslip, then enter stake
      setTimeout(function() { enterStake(cmd); }, 800);
    }, 300);
  }

  function enterStake(cmd) {
    var stake = cmd.stake;
    if (!stake) {
      log('No stake — selection added to betslip only');
      ackCommand(cmd.id, true, null);
      return;
    }

    // Find stake input in betslip
    var stakeInput = qs(document, BS.stakeInput);
    if (!stakeInput) {
      // Broader search: any visible number input
      var allInputs = qsa(document, 'input[type="number"], input[type="text"]');
      for (var i = 0; i < allInputs.length; i++) {
        var inp = allInputs[i];
        if (inp.offsetParent !== null && (inp.placeholder || '').toLowerCase().match(/stake|amount|bet/)) {
          stakeInput = inp;
          break;
        }
      }
    }
    if (!stakeInput) {
      warn('Stake input not found');
      ackCommand(cmd.id, true, 'Clicked but stake input not found');
      return;
    }

    // Set value (Angular-compatible)
    var nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    nativeSetter.call(stakeInput, String(stake));
    stakeInput.dispatchEvent(new Event('input', { bubbles: true }));
    stakeInput.dispatchEvent(new Event('change', { bubbles: true }));
    stakeInput.dispatchEvent(new Event('blur', { bubbles: true }));
    log('Stake set to ' + stake);

    setTimeout(function() {
      var confirmBtn = qs(document, BS.confirmBtn);
      if (!confirmBtn) {
        // Broader: any button with bet-related text
        var btns = qsa(document, 'button');
        for (var i = 0; i < btns.length; i++) {
          var t = getText(btns[i]).toLowerCase();
          if (t.indexOf('place') !== -1 || t.indexOf('bet') !== -1 || t.indexOf('accept') !== -1) {
            confirmBtn = btns[i];
            break;
          }
        }
      }
      if (!confirmBtn) {
        warn('Confirm button not found');
        ackCommand(cmd.id, false, 'Confirm button not found');
        return;
      }

      confirmBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      log('Clicked place bet');

      setTimeout(function() {
        var errEl = qs(document, BS.error);
        if (errEl && getText(errEl)) {
          warn('Bet error: ' + getText(errEl));
          ackCommand(cmd.id, false, getText(errEl));
        } else {
          log('Bet placed');
          ackCommand(cmd.id, true, null);
        }
      }, 1500);
    }, 500);
  }

  function ackCommand(cmdId, success, error, actualPrice) {
    fetch(API_BASE + '/commands/ack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: cmdId, success: success, error: error || null, actual_price: actualPrice || null,
      }),
    }).catch(function(e) { warn('Ack failed: ' + e.message); });
  }


  // ── Main loop ────────────────────────────────────────────────
  function tick() {
    _bootTicks++;
    var markets = scrapeMarkets();

    if (markets.length > 0) {
      _mode = 'MARKETS_VISIBLE';
      sendSnapshot(markets);
      if (_bootTicks <= 5) {
        log('Found ' + markets.length + ' market(s):');
        markets.forEach(function(m) {
          log('  ' + m.home_team + ' vs ' + m.away_team +
              ' | Line: ' + m.line + ' | Over: ' + m.over_price + ' Under: ' + m.under_price +
              ' | Score: ' + m.home_score + '-' + m.away_score +
              ' [' + m.source + ']');
        });
      }
    } else {
      _mode = 'NO_MARKETS';
      if (Date.now() - _lastSendTime > HEARTBEAT_MS) {
        sendSnapshot([]);
      }
      if (_bootTicks <= 3) {
        warn('No markets found (tick #' + _bootTicks + ')');
        // Log what we DO see
        var evContainer = qs(document, EV.container);
        var groupHeads = qsa(document, EV.marketGroupHead);
        var mktEls = qsa(document, EV.market);
        warn('  Event container: ' + (evContainer ? 'YES' : 'NO') +
             ' | Market groups: ' + groupHeads.length +
             ' | Markets: ' + mktEls.length);
        if (groupHeads.length > 0) {
          for (var i = 0; i < Math.min(groupHeads.length, 5); i++) {
            var t = getText(qs(groupHeads[i], EV.marketGroupTitle));
            warn('  Group: "' + t + '"');
          }
        }
      }
    }

    window._cb2k_timer = setTimeout(tick, POLL_MS[_mode]);
  }


  // ── Debug helpers ────────────────────────────────────────────
  window.cb2kStatus = function() {
    var markets = scrapeMarkets();
    console.group('%c[CB2K] Status', 'color: #00bcd4; font-weight: bold; font-size: 14px;');
    log('Version: 3.0 | Session: ' + _sessionId);
    log('Mode: ' + _mode + ' | Ticks: ' + _bootTicks + ' | Snapshots: ' + _n);
    log('Page: ' + (location.pathname.indexOf('/event-view/') !== -1 ? 'EVENT VIEW' : 'LIST VIEW'));
    log('Markets found: ' + markets.length);
    markets.forEach(function(m, i) {
      log('[' + i + '] ' + m.home_team + ' vs ' + m.away_team);
      log('    Score: ' + m.home_score + '-' + m.away_score + ' | Period: ' + m.period + ' ' + m.clock);
      log('    Line: ' + m.line + ' | Over: ' + m.over_price + ' | Under: ' + m.under_price);
      log('    Title: ' + m.market_title + ' | Full game: ' + m.is_full_game + ' [' + m.source + ']');
    });
    console.groupEnd();
    return markets;
  };

  window.cb2kDom = function() {
    console.group('%c[CB2K] DOM Scan', 'color: #ff9800; font-weight: bold;');
    log('Event container: ' + (qs(document, EV.container) ? 'YES' : 'NO'));
    log('Teams: ' + qsa(document, EV.teamName).length);
    qsa(document, EV.teamName).forEach(function(el) { log('  "' + getText(el) + '"'); });
    log('Score items: ' + qsa(document, EV.scoreItem).length);
    log('Market groups: ' + qsa(document, EV.marketGroupHead).length);
    qsa(document, EV.marketGroupHead).forEach(function(el) {
      log('  Group: "' + getText(qs(el, EV.marketGroupTitle)) + '"');
    });
    log('Markets (.market-bc): ' + qsa(document, EV.market).length);
    log('Market names (.market-name-bc): ' + qsa(document, EV.marketName).length);
    var names = {};
    qsa(document, EV.marketName).forEach(function(el) {
      var t = getText(el); names[t] = (names[t] || 0) + 1;
    });
    Object.keys(names).forEach(function(n) { log('  "' + n + '" x' + names[n]); });
    log('Odds (.market-odd-bc): ' + qsa(document, EV.marketOdd).length);
    console.groupEnd();
  };

  window.discoverSelectors = window.cb2kDom;


  // ── Boot ─────────────────────────────────────────────────────
  if (window._cb2k_injected) {
    log('Already injected, skipping');
    return;
  }
  window._cb2k_injected = true;

  var urlInfo = parseUrl();
  log('CB2K v3.0 | ' + _sessionId);
  log('Page: ' + (urlInfo.isEventView ? 'EVENT VIEW' : 'LIST/OTHER'));
  if (urlInfo.isEventView) {
    log('Game: ' + urlInfo.homeTeam + ' vs ' + urlInfo.awayTeam + ' (ID: ' + urlInfo.gameId + ')');
  }
  log('API: ' + API_BASE);
  log('Commands: cb2kStatus() | cb2kDom()');

  // Delay boot to let Angular render
  setTimeout(function() {
    tick();
    pollCommands();
  }, 2000);

})();
