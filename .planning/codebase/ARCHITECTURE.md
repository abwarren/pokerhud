# Architecture

**Analysis Date:** 2026-04-29

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Chrome Extension (PokerBet HUD)                           │
│                   `pokerhud/extension/`                                      │
├──────────────────┬──────────────────┬────────────────────────────────────────┤
│  Content Script  │  Background SW   │  Popup UI                             │
│  (DOM Scraper)   │  (Message Hub)   │  (React)                              │
│  `src/content/`  │  `src/background/`│  `src/popup/`                        │
└────────┬─────────┴────────┬─────────┴──────────────┬─────────────────────────┘
         │                  │                         │
         ▼                  ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Shared Library (`pokerhud/shared/`)                      │
│  Types, Parser, Stats Calculator, AI Client, Supabase Client                │
└────────┬──────────────────┬─────────────────────────┬───────────────────────┘
         │                  │                         │
         ▼                  ▼                         ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────────────────┐
│ Supabase Cloud   │ │ HUD Backend API  │ │ Dublin Flask Backend             │
│ (Postgres)       │ │ potlimitomaha.xyz│ │ `dublin-mirror/plo-w4p/app.py`   │
│ kzqrdtagpy...    │ │ /api/hud/*       │ │ Remote Control + Equity Engine   │
└──────────────────┘ └──────────────────┘ └──────────────────────────────────┘
         ▲                  ▲
         │                  │
┌────────┴──────────────────┴─────────────────────────────────────────────────┐
│                    Web Dashboard (`pokerhud/web/`)                           │
│                    React + Vite + TailwindCSS                                │
│                    Routes: / /players /games /import /settings /master       │
└─────────────────────────────────────────────────────────────────────────────┘
         ▲
         │
┌─────────────────────────────────────────────────────────────────────────────┐
│             Python Workers (Local PostgreSQL)                                │
│  `workers/worker1_lobby_scraper.py` through `worker5_timeseries_ledger.py`  │
│  `hud_dashboard.py`  `dashboard.py`  `tournament_scraper.py`                │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Content Script | DOM scraping, HUD overlay injection, polling PokerBet table state | `pokerhud/extension/src/content/index.tsx` |
| Background Service Worker | Message routing, API calls, snapshot forwarding, AI queue | `pokerhud/extension/src/background/index.ts` |
| Import Processor | Parse hand logs, create player/hand records in Supabase | `pokerhud/extension/src/background/import-processor.ts` |
| AI Analysis Service | Queue and process player analysis via OpenRouter | `pokerhud/extension/src/background/ai-service.ts` |
| Shared Types | TypeScript interfaces for Player, Hand, Stats, Game, Notes | `pokerhud/shared/types/` |
| Shared Parser | CSV/log parsing for PokerNow format hand histories | `pokerhud/shared/utils/parser.ts` |
| Stats Calculator | VPIP, PFR, 3-bet, AF, positional stats from raw hands | `pokerhud/shared/utils/stats-calculator.ts` |
| Supabase Client | All CRUD operations against Supabase Postgres | `pokerhud/shared/utils/supabase.ts` |
| Player Classifier | Classify players as TAG/LAG/LP/TP/Maniac/Fish | `pokerhud/shared/utils/player-classifier.ts` |
| Hand Advisor | GTO + exploitative advice (rule-based + AI) | `pokerhud/shared/utils/hand-advisor.ts` |
| Web Dashboard | Player stats UI, game management, import, live tables | `pokerhud/web/src/` |
| HUD Dashboard (Python) | Flask API serving tournament stats from local Postgres | `hud_dashboard.py` |
| Dublin Remote Control | Flask app for remote poker bot control, seat management | `dublin-mirror/plo-w4p/app.py` |
| Workers | Lobby scraping, tournament tracking, results, ICM, timeseries | `workers/` |
| Tournament Scraper | WebSocket + REST scraping of BetConstruct tournament data | `tournament_scraper.py` |

## Pattern Overview

**Overall:** Multi-layered client-side architecture with Chrome Extension as primary runtime, backed by dual data stores (Supabase cloud + local Postgres).

**Key Characteristics:**
- Chrome Extension Manifest V3 with service worker background
- Monorepo with npm workspaces (extension, web, shared)
- Content script injects React HUD overlay directly into PokerBet pages
- Background service worker acts as message bus and API gateway
- Shared library provides all business logic (parser, stats, DB access)
- Dual backend strategy: Supabase for persistent data, local Flask for real-time HUD

## Layers

**Presentation Layer (Chrome Extension Content Script):**
- Purpose: Scrape live poker table DOM state and render HUD overlay
- Location: `pokerhud/extension/src/content/`
- Contains: DOM scrapers, React HUD components, floating stat modules
- Depends on: Chrome APIs, Background Service Worker (via messaging)
- Used by: End user viewing PokerBet in Chrome

**Presentation Layer (Web Dashboard):**
- Purpose: Player database viewing, stats analysis, game management
- Location: `pokerhud/web/src/`
- Contains: React pages, components, routing
- Depends on: Shared library (Supabase client, types)
- Used by: End user browsing the dashboard

**Service Layer (Background Service Worker):**
- Purpose: Message routing, API orchestration, data forwarding
- Location: `pokerhud/extension/src/background/`
- Contains: Message handlers, AI service, import processor, scraper service
- Depends on: Shared library, Chrome APIs, external APIs (HUD backend, Supabase)
- Used by: Content scripts, popup

**Business Logic Layer (Shared):**
- Purpose: Core poker logic - parsing, statistics, classification, AI
- Location: `pokerhud/shared/`
- Contains: Types, utilities, parsers, calculators, DB access
- Depends on: Supabase SDK, OpenRouter API
- Used by: Extension background, web dashboard

**Data Layer:**
- Purpose: Persistent storage of players, hands, stats, tournaments
- Location: Supabase cloud (UUID `kzqrdtagpykoylhuqcyv`) + local Postgres (`pokerhud` database)
- Contains: Tables for users, games, hands, unified_players, player_stats, tournaments
- Depends on: PostgreSQL
- Used by: All components via Supabase JS client or psycopg2

**Infrastructure Layer (Dublin Server):**
- Purpose: Remote bot control, equity engine, live HUD API
- Location: `dublin-mirror/plo-w4p/`
- Contains: Flask app, nginx config, systemd services, static files
- Depends on: Flask, Flask-Login, Flask-Limiter, gunicorn
- Used by: Extension (snapshot forwarding), remote control UI

## Data Flow

### Primary Flow: Live Table Scraping

1. Content script polls PokerBet DOM every 2 seconds (`pokerhud/extension/src/content/index.tsx:349`)
2. `scrape()` function extracts players, cards, pot, dealer position from DOM selectors
3. Deduplication check: JSON comparison against last payload
4. On change, sends `POKERBET_SNAPSHOT` message to background service worker
5. Background forwards snapshot to HUD backend (`potlimitomaha.xyz/api/v2/snapshot`) and Supabase (`live_games` table)

### Secondary Flow: Hand Import Pipeline

1. Scraped log entries or CSV hand histories arrive via `SCRAPED_LOG` / `IMPORT_LOG_DATA` message
2. `ImportProcessor.processImport()` invoked (`pokerhud/extension/src/background/import-processor.ts:25`)
3. `parseHandHistory()` from shared parser converts log lines to `Hand[]` objects
4. Filters applied: only No Limit Hold'em, more than 3 players
5. Hands batch-inserted to Supabase `hands` table (chunks of 100)
6. For each player in imported hands: find/create `unified_player`, create `player_alias`, calculate stats
7. Stats written via `upsertPlayerStats()` then aggregated via `recalculateUnifiedPlayerStats()`

### Flow: AI Player Analysis

1. AI Analysis Service checks queue every 5 minutes (`pokerhud/extension/src/background/index.ts:538`)
2. For each queued player, fetches stats from chrome.storage
3. Calls OpenRouter API (Claude model) with player stats prompt
4. Receives player type, threat level, exploitative takeaways
5. Updates `ai_analysis` field on `unified_players` record

### Flow: Tournament Lobby Scraping

1. Content script checks lobby every 10 seconds (every 5th poll cycle)
2. `scrapeTournamentLobby()` walks DOM tree for ZAR amount patterns
3. Parsed tournaments sent via `TOURNAMENT_LOBBY_UPDATE` message
4. Background pushes each tournament to Supabase `tournaments` table

**State Management:**
- Chrome extension uses `chrome.storage.local` for auth, module positions, cached data
- Web dashboard uses `localStorage` for auth session
- Background service worker uses in-memory state (last payload JSON for dedup, AI queue)
- Dublin Flask server uses in-memory dicts with disk persistence for tables/commands

## Key Abstractions

**UnifiedPlayer:**
- Purpose: Cross-game player identity with aggregated statistics
- Examples: `pokerhud/shared/types/player.ts`, `pokerhud/shared/utils/supabase.ts`
- Pattern: One player may have multiple aliases (different names across games), unified by user assignment

**Hand:**
- Purpose: Complete hand history with actions per street, players, board, result
- Examples: `pokerhud/shared/types/hand.ts`
- Pattern: Stored as structured JSONB in Supabase, parsed from PokerNow CSV format

**AggregateStats:**
- Purpose: All computed poker statistics (VPIP, PFR, 3-bet, AF, c-bet, etc.)
- Examples: `pokerhud/shared/types/stats.ts`
- Pattern: Weighted average aggregation across all games for a unified player

**PlayerType Classification:**
- Purpose: Categorize players as TAG/LAG/LP/TP/Maniac/Fish based on VPIP/PFR thresholds
- Examples: `pokerhud/shared/types/player.ts:114` (thresholds), `pokerhud/shared/utils/player-classifier.ts`
- Pattern: Rule-based classification with defined VPIP/PFR ranges per type

## Entry Points

**Chrome Extension Content Script:**
- Location: `pokerhud/extension/src/content/index.tsx`
- Triggers: Injected on PokerBet pages matching manifest content_scripts patterns
- Responsibilities: DOM scraping, HUD rendering, message forwarding

**Chrome Extension Background:**
- Location: `pokerhud/extension/src/background/index.ts`
- Triggers: Chrome extension lifecycle, message events from content scripts
- Responsibilities: API calls, data persistence, AI analysis orchestration

**Web Dashboard:**
- Location: `pokerhud/web/src/main.tsx` -> `pokerhud/web/src/App.tsx`
- Triggers: User navigates to dashboard URL
- Responsibilities: Player stats viewing, game management, data import

**HUD Dashboard (Python):**
- Location: `hud_dashboard.py`
- Triggers: HTTP requests to `/api/hud/*`
- Responsibilities: Serve tournament player stats from local Postgres

**Dublin Flask App:**
- Location: `dublin-mirror/plo-w4p/app.py`
- Triggers: HTTP requests proxied via nginx at potlimitomaha.xyz
- Responsibilities: Remote table control, snapshot storage, equity engine, bot deployment

**Python Workers:**
- Location: `workers/worker1_lobby_scraper.py` through `workers/worker5_timeseries_ledger.py`
- Triggers: Scheduled execution (cron/manual)
- Responsibilities: Background data collection from PokerBet APIs

## Architectural Constraints

- **Threading:** Extension uses single-threaded event loop (Chrome service worker). Dublin Flask uses background threads for stale seat eviction and state persistence.
- **Global state:** Dublin Flask app uses module-level dicts (`_tables`, `_command_queue`, `_bot_seats`) protected by `_store_lock` threading.Lock.
- **Dual data stores:** Supabase (cloud, extension/web) and local PostgreSQL (workers, Python dashboards) are NOT synchronized automatically. Extension writes to Supabase; workers write to local Postgres.
- **Rate limiting:** Dublin app uses flask-limiter (1 snapshot/sec per IP). Extension deduplicates snapshots client-side. Supabase live_games push throttled to 10s intervals.
- **Auth model:** Extension uses password-hash-based anonymous auth via Supabase. Dublin Flask uses Flask-Login with session cookies. No shared auth between systems.

## Anti-Patterns

### Dual Database Without Sync

**What happens:** Hand histories in Supabase (via extension) and tournament stats in local Postgres (via workers) exist in separate stores with no synchronization mechanism.
**Why it's wrong:** Queries joining player data across both stores require manual correlation. The `hud_dashboard.py` reads local Postgres while extension reads Supabase.
**Do this instead:** Consolidate on one store or implement a sync layer. Currently `workers/dublin_sync.py` exists but only handles one direction.

### Hardcoded Supabase Credentials in Source

**What happens:** Supabase URL and anon key are hardcoded in `pokerhud/extension/src/background/index.ts:412-413` and `pokerhud/shared/utils/supabase.ts:3-4`.
**Why it's wrong:** Credentials are committed to git. The anon key is public-facing by design (RLS protects data), but the pattern makes rotation difficult.
**Do this instead:** Use environment variables exclusively with build-time injection. The env vars are already set up (`VITE_SUPABASE_URL`) but fallback to hardcoded values.

### Content Script Inlining Scraper Logic

**What happens:** `pokerhud/extension/src/content/index.tsx` contains ~130 lines of inline scraper logic duplicated from `pokerhud/shared/scrapers/pokerbet.js`.
**Why it's wrong:** Two implementations of the same scraper that can diverge. Bug fixes must be applied in both places.
**Do this instead:** Import from the shared scraper module at build time, or consolidate to one implementation.

## Error Handling

**Strategy:** Try/catch with silent failure and logging. No global error boundary in extension.

**Patterns:**
- Background service worker wraps all message handlers in try/catch, returns `{ success: false, error: message }` on failure
- Supabase operations return `null` on error after `console.error()` logging
- Content script scraper uses try/catch around iframe access (may fail due to cross-origin) with silent retry on next poll cycle
- Dublin Flask uses `@app.errorhandler` decorators for 413, 429, 500 responses
- HUD backend API fallback: tries `potlimitomaha.xyz` first, falls back to `127.0.0.1:5001`

## Cross-Cutting Concerns

**Logging:** `console.log` / `console.error` in TypeScript (extension/web). Python `logging` module in workers/dashboards. Dublin Flask uses `app.logger` routed to systemd/journald.

**Validation:** Minimal explicit validation. Hand import filters by game type and player count. Rate limiting on Dublin Flask API endpoints.

**Authentication:** Extension uses password hash lookup in Supabase `users` table. Web dashboard stores auth in localStorage. Dublin uses Flask-Login with cookie sessions. Workers use Supabase service role key directly.

---

*Architecture analysis: 2026-04-29*
