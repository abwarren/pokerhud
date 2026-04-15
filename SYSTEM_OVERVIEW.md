# HUD System Overview

**Date:** 2026-04-13  
**Location:** `/home/warrenabrahams/HUD`  
**Status:** Understanding Phase

---

## 🎯 What We Have

### 1. PokerNow HUD (Complete System)
**Source:** https://github.com/misternighguy/pokerhud  
**Status:** Production-ready codebase (5,000+ LOC, 81+ files)

**Architecture:**
```
pokerhud/
├── extension/        Chrome Extension (Manifest V3)
│   ├── popup/       React UI (login, dashboard, quick stats)
│   ├── content/     HUD overlay (stat boxes, modals)
│   └── background/  Service worker (AI queue, scraper, import)
├── web/             React Dashboard (game/player management)
├── shared/          TypeScript utilities (parser, stats, AI)
└── supabase/        8-table PostgreSQL schema
```

**Key Features:**
- ✅ Password-protected ("aksuited")
- ✅ Real-time HUD overlay on PokerNow.club
- ✅ 15+ poker stats (VPIP, PFR, 3-Bet, AF, WTSD, W$SD, C-Bet, etc.)
- ✅ AI exploitative analysis (OpenRouter + Claude Opus)
- ✅ Player alias/merge system
- ✅ Notes system (tendencies, tags, quick notes)
- ✅ GTO hand advisor (hybrid rule-based + AI)
- ✅ Hand history parser (PokerNow format)
- ✅ Positional breakdowns (8 positions)
- ✅ Player type classification (TAG/LAG/LP/TP/Maniac/Fish)

### 2. ScrapeGraph-ai
**Source:** https://github.com/ScrapeGraphAI/Scrapegraph-ai  
**Purpose:** AI-powered web scraping using LLMs

**Capabilities:**
- Web scraping with natural language prompts
- Playwright-based browser automation
- Supports multiple LLMs (OpenAI, Groq, Ollama, Gemini)
- Multi-page scraping pipelines

### 3. PingCAP SQL Parser
**Source:** https://github.com/pingcap/parser  
**Purpose:** Go-based SQL parser for TiDB/MySQL

---

## 🤔 Integration Options

### Option A: Standalone PokerNow HUD
Build the PokerNow HUD as-is for PokerNow.club tables:
- Chrome extension for real-time overlay
- Web dashboard for analysis
- Supabase backend
- AI-powered insights

### Option B: Integrate with PLO Remote Control
Adapt the HUD for your existing poker infrastructure:
- **Target:** nuts4poker.com (PokerBet, JetWin, GoldRush)
- **Backend:** Dublin server (52.16.14.220)
- **Players:** 9 KasmVNC containers (bot-kele1 through bot-hele)
- **Current System:** Flask API + hand collector + remote control UI
- **Integration Points:**
  - Parse hand histories from your `/opt/plo-equity/hand-collector/`
  - Display HUD on your remote control UI at `/`
  - Store stats in your existing backend
  - Use AI analysis for exploitative play

### Option C: Multi-Site HUD
Build a universal HUD that works across:
- PokerNow.club
- nuts4poker.com (PokerBet)
- nuts4poker.com (JetWin)
- nuts4poker.com (GoldRush)

### Option D: Custom Scraping + Analysis System
Use ScrapeGraph-ai to:
- Scrape poker site data
- Parse with SQL parser
- Analyze with AI
- Build custom HUD

---

## 📋 Next Steps

**WAITING FOR DIRECTION:**

1. **What's the primary use case?**
   - PokerNow.club HUD? (standalone)
   - Integration with PLO Remote Control system?
   - Multi-site HUD?
   - Custom scraping/analysis system?

2. **What's the target?**
   - Which poker site(s)?
   - Existing infrastructure or new build?
   - Live play or analysis?

3. **What features are priority?**
   - Real-time HUD overlay?
   - Hand history analysis?
   - AI exploitative insights?
   - Player tracking?
   - GTO recommendations?

4. **Tech preferences?**
   - Use existing Flask backend or new Supabase?
   - Chrome extension or web-based?
   - Local or cloud deployment?

---

## 💡 Recommendations

Given your existing PLO Remote Control infrastructure, I recommend:

**Phase 1: HUD Integration**
1. Adapt PokerNow parser for nuts4poker.com format
2. Integrate with existing Flask API (`/api/table/latest`)
3. Add HUD overlay to remote control UI
4. Use existing hand collector data

**Phase 2: Stats System**
5. Implement stats calculator (VPIP, PFR, etc.)
6. Store in PostgreSQL or existing DB
7. Display in real-time during play

**Phase 3: AI Analysis**
8. Integrate OpenRouter + Claude
9. Generate exploitative takeaways
10. Hand advisor for decision making

**Phase 4: Advanced Features**
11. Player management (alias merging)
12. Notes system
13. Multi-game tracking
14. Historical analysis

---

**Ready to proceed once you confirm the direction! 🎯**
