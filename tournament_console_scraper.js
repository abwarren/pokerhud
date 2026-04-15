// ============================================================
// POKERBET TOURNAMENT LOBBY SCRAPER
// ============================================================
// Paste this into Chrome DevTools Console while on the
// poker client tournament lobby page:
//   poker-web.pokerbet.co.za/18751019/#/product/3/3/tournament-cat/1
//
// It scrapes all visible tournament data from the DOM.
// ============================================================

(function scrapeTournaments() {
  const results = {
    scraped_at: new Date().toISOString(),
    url: window.location.href,
    tournaments: [],
    cash_tables: [],
    lobby_tabs: [],
    raw_elements: []
  };

  // 1. Find the document (might be in iframe)
  let doc = document;
  const frames = document.querySelectorAll('iframe');
  for (const frame of frames) {
    try {
      if (frame.contentDocument && frame.contentDocument.querySelector('sg-app')) {
        doc = frame.contentDocument;
        results.in_iframe = true;
        break;
      }
    } catch(e) { /* cross-origin */ }
  }

  // 2. Scrape lobby navigation tabs
  const tabSelectors = [
    '.lobby-tabs button', '.lobby-tabs a', '.tab-item',
    '[class*="category"]', '[class*="tab"]', '.nav-item',
    'sg-lobby-category', '.lobby-category'
  ];
  for (const sel of tabSelectors) {
    doc.querySelectorAll(sel).forEach(el => {
      const text = (el.textContent || '').trim();
      if (text && text.length < 50) {
        results.lobby_tabs.push({
          text: text,
          class: el.className,
          tag: el.tagName,
          active: el.classList.contains('active') || el.classList.contains('selected')
        });
      }
    });
  }

  // 3. Scrape tournament list items
  const tournamentSelectors = [
    // BetConstruct tournament row patterns
    '[class*="tournament-row"]',
    '[class*="tournament-item"]',
    '[class*="tournament-list"] > *',
    '[class*="mtt-row"]',
    '[class*="sit-and-go"]',
    'sg-tournament-row',
    'sg-tournament-item',
    // Table/grid rows in lobby
    '.lobby-table-row',
    '[class*="lobby"] tr',
    '[class*="lobby"] [class*="row"]',
    // Generic list items in lobby area
    '.table-list-item',
    '[class*="table-item"]',
    '[class*="game-row"]',
    '[class*="game-item"]',
  ];

  for (const sel of tournamentSelectors) {
    doc.querySelectorAll(sel).forEach(el => {
      const text = (el.textContent || '').trim();
      if (text.length > 5 && text.length < 2000) {
        results.raw_elements.push({
          selector: sel,
          text: text.substring(0, 500),
          class: el.className,
          childCount: el.children.length
        });
      }
    });
  }

  // 4. Try to access Angular component data
  try {
    const sgApp = doc.querySelector('sg-app');
    if (sgApp && sgApp.__ngContext__) {
      results.angular_detected = true;
    }
  } catch(e) {}

  // 5. Scrape ALL visible text blocks that look like tournament data
  const allTextNodes = [];
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_ELEMENT, null);
  let node;
  while (node = walker.nextNode()) {
    const text = (node.textContent || '').trim();
    const cls = (node.className || '').toString().toLowerCase();

    // Check for tournament-related content
    if (cls.includes('tournament') || cls.includes('mtt') ||
        cls.includes('sit-and-go') || cls.includes('spin') ||
        cls.includes('freeroll') || cls.includes('satellite') ||
        cls.includes('lobby') || cls.includes('schedule')) {
      if (text.length > 3 && text.length < 1000) {
        results.tournaments.push({
          class: node.className.toString().substring(0, 200),
          tag: node.tagName,
          text: text.substring(0, 500),
          rect: node.getBoundingClientRect()
        });
      }
    }

    // Check for table-like data (names with buy-ins, player counts)
    if (cls.includes('table') || cls.includes('row') || cls.includes('list')) {
      const hasAmount = /R\s*\d|ZAR|\$\d/i.test(text);
      const hasPlayers = /\d+\s*\/\s*\d+|\d+\s*player/i.test(text);
      const hasTime = /\d+:\d+|pm|am/i.test(text);
      if ((hasAmount || hasPlayers || hasTime) && text.length < 500) {
        results.cash_tables.push({
          text: text.substring(0, 300),
          class: cls.substring(0, 100),
          has_amount: hasAmount,
          has_players: hasPlayers,
          has_time: hasTime
        });
      }
    }
  }

  // 6. Get page structure overview
  results.page_structure = {
    title: doc.title,
    body_classes: (doc.body.className || '').toString(),
    sg_app: !!doc.querySelector('sg-app'),
    total_elements: doc.querySelectorAll('*').length,
    buttons: Array.from(doc.querySelectorAll('button')).map(b => b.textContent.trim()).filter(t => t.length > 0 && t.length < 50),
    links: Array.from(doc.querySelectorAll('a[href]')).map(a => ({text: a.textContent.trim().substring(0,50), href: a.href})).filter(l => l.text.length > 0).slice(0, 30)
  };

  // Output
  console.log('=== POKERBET TOURNAMENT SCRAPE ===');
  console.log(`Tournaments found: ${results.tournaments.length}`);
  console.log(`Cash tables found: ${results.cash_tables.length}`);
  console.log(`Lobby tabs: ${results.lobby_tabs.length}`);
  console.log(`Raw elements: ${results.raw_elements.length}`);
  console.log('Full results:', JSON.stringify(results, null, 2));

  // Copy to clipboard
  try {
    copy(JSON.stringify(results, null, 2));
    console.log('Results copied to clipboard!');
  } catch(e) {
    console.log('(Could not copy to clipboard - use copy() manually)');
  }

  return results;
})();
