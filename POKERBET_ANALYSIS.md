# PokerBet.co.za HUD Integration Analysis

**Date:** 2026-04-13  
**Target Site:** pokerbet.co.za  
**Task:** Adapt PokerNow HUD for PokerBet  
**Status:** Planning Phase (No Execution)

---

## 🎯 Clarification Needed

**QUESTION:** Are these the same or different?
- **pokerbet.co.za** (public South African poker site)
- **nuts4poker.com** with PokerBet subdomain (your existing infrastructure)

### Scenario A: They're the SAME
If pokerbet.co.za routes to your nuts4poker.com infrastructure:
- ✅ You already have backend infrastructure (Dublin 52.16.14.220)
- ✅ You already have hand collector system
- ✅ You already have Flask API with table data
- ✅ Integration is simpler (adapt existing remote control UI)

### Scenario B: They're DIFFERENT
If pokerbet.co.za is a separate third-party site:
- ❌ Need to scrape/parse external site
- ❌ No backend access
- ❌ Chrome extension approach required
- ❌ Reverse engineering needed

---

## 🔍 Site Analysis: pokerbet.co.za

### Initial Findings

**Technology Stack:**
```
✅ JavaScript-required SPA (Single Page Application)
✅ Client-side rendered (no server-side markup)
✅ Facebook Pixel tracking (IDs: 1212048250298692, 938384098115235)
✅ Twitter conversion tracking ("onbsz")
⚠️  Full DOM structure not accessible without JS execution
```

**What We Know:**
- Heavy JavaScript dependency
- Commercial gambling platform
- Sophisticated analytics/tracking
- Web-based (no download required)

**What We DON'T Know Yet:**
- ❓ Table rendering method (DOM/Canvas/WebGL/iframe)
- ❓ Player positioning system
- ❓ Game state data structure
- ❓ Action button IDs/classes
- ❓ Hand history format
- ❓ WebSocket vs polling for real-time updates
- ❓ Framework (React/Vue/Angular/vanilla)
- ❓ API endpoints (if any)

### Required Deep Dive (Manual Analysis Needed)

To properly adapt the HUD, we need:

1. **Live Browser Session Analysis**
   - Open pokerbet.co.za in Chrome
   - Enable Developer Tools
   - Inspect table DOM structure
   - Monitor Network tab for API calls
   - Capture WebSocket/SSE connections
   - Record hand history format

2. **DOM Structure Mapping**
   ```javascript
   // Need to identify selectors like:
   const SELECTORS = {
     playerSeats: '???',        // Player seat containers
     playerNames: '???',        // Player name elements
     playerStacks: '???',       // Stack size display
     playerCards: '???',        // Hole cards (if visible)
     communityCards: '???',     // Board cards
     pot: '???',                // Pot size
     actionButtons: '???',      // Fold/Call/Raise buttons
     handHistory: '???',        // Hand history log
     gameId: '???',             // Current game identifier
   };
   ```

3. **Hand History Format**
   ```
   Example from PokerNow:
   "at 2024-01-15 14:32:01 -- Player1 posts a small blind of 1"
   "at 2024-01-15 14:32:01 -- Player2 posts a big blind of 2"
   "at 2024-01-15 14:32:03 -- Player3 folds"
   
   Need PokerBet equivalent format ↑
   ```

4. **Real-time Data Flow**
   - How does table state update? (WebSocket? Polling?)
   - What events trigger updates?
   - Can we intercept/observe these updates?

---

## 🏗️ Integration Approaches

### Option 1: Chrome Extension (Full HUD)
**Best if:** pokerbet.co.za is external third-party site

**Architecture:**
```
Chrome Extension
├── Content Script (injected into pokerbet.co.za)
│   ├── DOM Observer (watch for table changes)
│   ├── Hand History Scraper
│   ├── HUD Overlay (React component)
│   └── Position Calculator
├── Background Service Worker
│   ├── Stats Calculator
│   ├── AI Analysis Queue
│   └── Database Sync (Supabase)
└── Popup UI
    ├── Player Management
    ├── Game History
    └── Settings
```

**Pros:**
- ✅ Works on any site (no backend access needed)
- ✅ Portable (can adapt to other poker sites)
- ✅ User installs locally (you control updates)

**Cons:**
- ❌ Requires reverse engineering pokerbet.co.za
- ❌ Breaks if site updates significantly
- ❌ Limited to browser context
- ❌ Can't control player actions (read-only)

### Option 2: Backend Integration (Remote Control)
**Best if:** pokerbet.co.za = nuts4poker.com/PokerBet

**Architecture:**
```
Dublin Backend (52.16.14.220)
├── Flask API (existing)
│   ├── /api/table/latest (already working)
│   ├── /api/stats/player/<id> (NEW)
│   ├── /api/hud/snapshot (NEW)
│   └── /api/ai/analysis (NEW)
├── Stats Engine (NEW module)
│   ├── Parser (adapt for PokerBet format)
│   ├── Calculator (VPIP, PFR, etc)
│   └── Storage (PostgreSQL)
├── Hand Collector (existing)
│   └── Enhanced with stat tracking
└── Frontend (Cape Town 15.240.44.80)
    ├── Remote Control UI (existing at /)
    └── HUD Overlay (NEW component)
```

**Pros:**
- ✅ Leverage existing infrastructure
- ✅ Direct database access
- ✅ Can control player actions
- ✅ Unified system (hand collection + stats + HUD)

**Cons:**
- ❌ Only works for your infrastructure
- ❌ Requires backend deployment
- ❌ Needs coordination with existing systems

### Option 3: Hybrid Approach
**Best if:** Want both flexibility and integration

**Architecture:**
```
Chrome Extension (overlay only)
    ↓ (fetch stats)
Backend API (stats engine)
    ↓ (pull hands)
Hand Collector (existing)
```

**Pros:**
- ✅ Clean separation of concerns
- ✅ Extension is lightweight (just display)
- ✅ Backend handles heavy computation
- ✅ Can work with multiple sites

**Cons:**
- ❌ More complex architecture
- ❌ Requires both extension + backend work

---

## 📊 Comparison: PokerNow vs PokerBet

### PokerNow HUD Current Implementation

**Data Source:**
- Scrapes PokerNow.club hand history log
- Parses text-based format
- Regex patterns for actions

**Integration Method:**
- Chrome extension content script
- Observes DOM mutations
- Injects React overlay

**Key Files:**
```
pokerhud/shared/utils/parser.ts         - PokerNow-specific parser
pokerhud/extension/src/content/pokernow-observer.ts  - DOM observer
pokerhud/extension/src/content/hud-overlay.tsx       - HUD UI
```

### PokerBet Adaptation Required

**Must Create:**
1. PokerBet parser (`pokerbet-parser.ts`)
2. PokerBet DOM observer (`pokerbet-observer.ts`)
3. PokerBet selector config (`pokerbet-selectors.ts`)
4. Site detection logic (`site-detector.ts`)

**Must Modify:**
1. Content script entry point (detect site)
2. HUD positioning (match PokerBet layout)
3. Stats display (adapt to PokerBet UI style)

**Can Reuse (unchanged):**
1. Stats calculator (`stats-calculator.ts`)
2. AI integration (`openrouter.ts`)
3. Player classifier (`player-classifier.ts`)
4. Database layer (`supabase.ts`)
5. Popup UI (works for any site)
6. Web dashboard (site-agnostic)

---

## 🎯 Next Steps (Pending Clarification)

### If PokerBet.co.za = Your Infrastructure:
1. ✅ Confirm it routes to nuts4poker.com
2. 📋 Document existing hand collector format
3. 📋 Review `/api/table/latest` data structure
4. 📋 Design stats API endpoints
5. 📋 Plan HUD component for remote control UI
6. 📋 Create database schema for stats storage

### If PokerBet.co.za = External Site:
1. 🔍 Manual browser analysis (DOM structure)
2. 🔍 Capture hand history format
3. 🔍 Identify WebSocket/API endpoints
4. 📋 Create PokerBet parser
5. 📋 Build Chrome extension
6. 📋 Test with live tables

---

## ❓ Questions for You

1. **Is pokerbet.co.za the same as your nuts4poker.com/PokerBet?**
   - YES → Backend integration approach
   - NO → Chrome extension approach

2. **Do you have access to PokerBet's backend/database?**
   - YES → Can read hand data directly
   - NO → Must scrape from frontend

3. **Primary use case?**
   - Assist YOUR players (9 bot containers)?
   - Assist HUMAN players on external site?
   - Both?

4. **HUD Display Location?**
   - Overlay on PokerBet tables?
   - Separate dashboard?
   - Integrated into remote control UI?

5. **Stats Priority?**
   - Essential only (VPIP, PFR, 3-Bet)?
   - Advanced (all 15+ stats)?
   - AI analysis (exploitative takeaways)?

---

**Waiting for clarification to proceed with detailed architecture design! 🎯**
