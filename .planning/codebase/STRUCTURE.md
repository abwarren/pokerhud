# Codebase Structure

**Analysis Date:** 2026-04-29

## Directory Layout

```
/opt/pokerhud/
├── pokerhud/                    # Main monorepo (npm workspaces)
│   ├── extension/               # Chrome Extension (Manifest V3)
│   │   ├── src/
│   │   │   ├── background/      # Service worker (message hub, AI, import)
│   │   │   ├── content/         # DOM scraper + HUD overlay (React)
│   │   │   ├── popup/           # Extension popup UI (React)
│   │   │   └── utils/           # Chrome storage helpers, constants
│   │   ├── dist/                # Built extension output
│   │   ├── manifest.json        # MV3 manifest
│   │   ├── package.json         # @pokernow-hud/extension
│   │   └── vite.config.ts       # Build config
│   ├── web/                     # Web Dashboard (React + Vite)
│   │   ├── src/
│   │   │   ├── components/      # Reusable UI components
│   │   │   ├── pages/           # Route pages (Dashboard, Players, etc.)
│   │   │   ├── App.tsx          # Router + auth wrapper
│   │   │   └── main.tsx         # Entry point
│   │   ├── dist/                # Built web output
│   │   ├── package.json         # @pokernow-hud/web
│   │   └── vite.config.ts       # Build config
│   ├── shared/                  # Shared library (types + utils)
│   │   ├── constants/           # GTO ranges JSON
│   │   ├── scrapers/            # PokerBet DOM scraper (JS)
│   │   ├── types/               # TypeScript interfaces
│   │   ├── utils/               # Parser, stats, AI, Supabase, auth
│   │   ├── index.ts             # Barrel export
│   │   └── package.json         # @pokernow-hud/shared
│   ├── supabase/                # Supabase config + migrations
│   │   └── migrations/          # SQL schema files
│   ├── tests/                   # Unit tests (parser, stats)
│   ├── scripts/                 # Build/migration scripts
│   └── package.json             # Root workspace package.json
├── dublin-mirror/               # Mirror of production Dublin server code
│   ├── plo-w4p/                 # Flask backend (remote control)
│   │   ├── app.py              # Main Flask app (entry point)
│   │   ├── equity_routes.py    # Equity engine SSE endpoints
│   │   ├── equity_engine.py    # PLO equity calculations
│   │   ├── auth_models.py      # User/session management
│   │   ├── auth_routes.py      # Login/logout/register
│   │   ├── audit_logs.py       # Activity logging
│   │   ├── blm_routes.py       # Basketball League Manager routes
│   │   ├── windows_routes.py   # Windows instance management
│   │   ├── w4p_relay.py        # W4P command relay
│   │   ├── w4p.js              # Browser-injected bot script
│   │   ├── static/             # Static HTML/JS/CSS served by Flask
│   │   ├── templates/          # Jinja2 templates
│   │   ├── hand-collector/     # Saved hand histories
│   │   └── goldrush-collector/ # GoldRush hands
│   ├── nginx-config/           # Nginx reverse proxy config
│   │   └── nginx.conf          # Full nginx config for potlimitomaha.xyz
│   ├── scripts/                # Infrastructure scripts
│   │   └── eip-snat-rules.sh   # EIP/SNAT routing rules
│   └── systemd-services/       # Service unit files
│       ├── plo-w4p.service
│       ├── plo-equity.service
│       ├── plo-engine.service
│       └── plo-collector.service
├── workers/                     # Python background workers
│   ├── worker1_lobby_scraper.py     # Tournament lobby discovery
│   ├── worker2_active_tracker.py    # Running tournament updates
│   ├── worker3_results_collector.py # Tournament results
│   ├── worker4_icm_snapshots.py     # ICM calculations
│   ├── worker5_timeseries_ledger.py # Player balance tracking
│   └── dublin_sync.py              # Sync data from Dublin
├── w4p-extension/               # Minimal W4P Chrome extension
│   ├── manifest.json
│   └── loader.js
├── supabase/                    # Root-level Supabase migrations
│   └── migrations/
├── dashboard/                   # Dashboard Python package (cached)
├── logs/                        # Worker log output
├── tournament_data/             # Scraped tournament JSON files
├── hud_dashboard.py            # Flask HUD stats API (tournament stats)
├── dashboard.py                # Flask time-series ledger dashboard
├── tournament_scraper.py       # BetConstruct WS+REST tournament scraper
├── tournament_scraper_live.py  # Live tournament scraper variant
├── ws_connect.py               # BetConstruct WebSocket protocol client
├── ws_discovery.py             # WebSocket protocol discovery
├── run_agent.py                # Anthropic API agent runner
├── setup_agent.py              # Agent setup script
├── nba_sync.py                 # NBA data sync (side project)
├── blm_engine.py               # Basketball League Manager engine
├── blm_dashboard.html          # BLM dashboard UI
├── cyber_dashboard.html        # Cybersecurity dashboard
├── cyber_q2_scanner.py         # Cyber scanner
├── snapshot_server.py          # Minimal snapshot test server
├── test_server.py              # Extension API test server
├── safe-promote-to-dublin.sh   # 6-gate safe deployment script
├── sync-from-dublin.sh         # Pull code from Dublin server
├── .env                        # Environment variables (DO NOT READ)
├── .gitignore                  # Git ignore rules
├── .mcp.json                   # MCP (Model Context Protocol) config
└── Scrapegraph-ai/             # Third-party scraping tool (vendored)
```

## Directory Purposes

**`pokerhud/extension/src/background/`:**
- Purpose: Chrome extension service worker - message routing, API orchestration
- Contains: `index.ts` (message handlers), `ai-service.ts` (AI queue), `import-processor.ts` (hand import), `scraper.ts` (auto-scrape), `pokerbet-api.js` (PokerBet API client)
- Key files: `index.ts` is the main entry point for all background processing

**`pokerhud/extension/src/content/`:**
- Purpose: Content scripts injected into poker sites - scraping + HUD rendering
- Contains: `index.tsx` (main entry + inline scraper), `pokerbet-content.tsx` (alt entry), `module-manager.tsx` (floating stat modules), `hud-overlay.tsx`, `site-detector.ts`, `pokerbet-observer.ts`, `pokernow-observer.ts`, `pokerbet-parser.ts`
- Key files: `index.tsx` is the active content script, `module-manager.tsx` manages floating HUD panels

**`pokerhud/extension/src/popup/`:**
- Purpose: Extension popup UI when user clicks extension icon
- Contains: `App.tsx` (main UI), `Dashboard.tsx`, `Login.tsx`, `QuickStats.tsx`

**`pokerhud/shared/types/`:**
- Purpose: All TypeScript type definitions shared across extension and web
- Contains: `player.ts`, `hand.ts`, `stats.ts`, `game.ts`, `auth.ts`, `notes.ts`, `index.ts` (barrel)
- Key files: `player.ts` defines `UnifiedPlayer`, `PlayerAlias`, `PlayerStats`, `AIAnalysis` and type classification thresholds

**`pokerhud/shared/utils/`:**
- Purpose: Core business logic - parsing, statistics, AI, database access
- Contains: `parser.ts` (PokerNow CSV parser), `stats-calculator.ts` (all poker stats), `supabase.ts` (all DB operations), `player-classifier.ts` (type classification), `openrouter.ts` (AI client), `hand-advisor.ts` (GTO + exploitative advice), `alias-detector.ts`, `auth.ts`
- Key files: `supabase.ts` (1390 lines - all CRUD), `stats-calculator.ts` (comprehensive stat calculations)

**`pokerhud/web/src/pages/`:**
- Purpose: Route-level page components for the web dashboard
- Contains: `Dashboard.tsx` (live games + overview), `Players.tsx` (player database with sorting/filtering), `Games.tsx` (game list), `Import.tsx` (hand import), `Settings.tsx`, `Master.tsx` (admin view), `Login.tsx`

**`pokerhud/web/src/components/`:**
- Purpose: Reusable UI components for the dashboard
- Contains: `PlayerCard.tsx`, `PlayerDetailModal.tsx`, `GameCard.tsx`, `MergeModal.tsx`, `NotesEditor.tsx`, `TimeseriesDashboard.tsx`

**`dublin-mirror/plo-w4p/`:**
- Purpose: Mirror of production Flask backend on Dublin EC2 server
- Contains: Flask app, authentication, equity engine, remote control UI, bot management, hand collectors
- Key files: `app.py` (main entry, 250+ routes), `equity_routes.py`, `auth_models.py`, `w4p.js` (browser bot script)

**`workers/`:**
- Purpose: Background Python workers for automated data collection
- Contains: 5 numbered workers for different scraping/tracking tasks plus Dublin sync
- Key files: `worker1_lobby_scraper.py` (tournament discovery), `worker5_timeseries_ledger.py` (balance tracking)

## Key File Locations

**Entry Points:**
- `pokerhud/extension/src/background/index.ts`: Extension background service worker
- `pokerhud/extension/src/content/index.tsx`: Content script injected on poker sites
- `pokerhud/web/src/main.tsx`: Web dashboard entry
- `dublin-mirror/plo-w4p/app.py`: Dublin Flask server entry
- `hud_dashboard.py`: Local HUD stats Flask API
- `dashboard.py`: Local time-series dashboard

**Configuration:**
- `pokerhud/package.json`: Root monorepo workspace config
- `pokerhud/extension/manifest.json`: Chrome extension manifest (MV3)
- `pokerhud/extension/vite.config.ts`: Extension build config
- `pokerhud/web/vite.config.ts`: Web dashboard build config
- `dublin-mirror/nginx-config/nginx.conf`: Production nginx routing
- `dublin-mirror/systemd-services/plo-w4p.service`: Flask service unit

**Core Logic:**
- `pokerhud/shared/utils/supabase.ts`: All Supabase CRUD operations (1390 lines)
- `pokerhud/shared/utils/stats-calculator.ts`: All poker statistics calculations
- `pokerhud/shared/utils/parser.ts`: PokerNow CSV hand history parser
- `pokerhud/shared/utils/player-classifier.ts`: Player type classification
- `pokerhud/shared/utils/openrouter.ts`: AI analysis via OpenRouter
- `pokerhud/shared/utils/hand-advisor.ts`: GTO + exploitative hand advice
- `pokerhud/extension/src/background/import-processor.ts`: Hand import pipeline

**Testing:**
- `pokerhud/tests/parser.test.ts`: Parser unit tests
- `pokerhud/tests/stats.test.ts`: Stats calculator unit tests
- `pokerhud/jest.config.js`: Test configuration

**Database Schema:**
- `pokerhud/supabase/migrations/20260413150000_hud_initial_schema.sql`: Full Supabase schema
- `supabase/migrations/20260413150000_hud_initial_schema.sql`: Root-level copy

**Deployment:**
- `safe-promote-to-dublin.sh`: 6-gate safe promotion script
- `sync-from-dublin.sh`: Pull production code to local mirror

## Naming Conventions

**Files:**
- TypeScript source: `kebab-case.ts` / `kebab-case.tsx` (e.g., `stats-calculator.ts`, `module-manager.tsx`)
- React pages: `PascalCase.tsx` (e.g., `Dashboard.tsx`, `Players.tsx`)
- React components: `PascalCase.tsx` (e.g., `PlayerCard.tsx`, `MergeModal.tsx`)
- Python files: `snake_case.py` (e.g., `hud_dashboard.py`, `tournament_scraper.py`)
- Workers: `worker{N}_{description}.py` (e.g., `worker1_lobby_scraper.py`)
- SQL migrations: `{timestamp}_{description}.sql`
- Backup files: `{original}.bak.{unix_timestamp}` or `{original}.bak.{YYYYMMDD_HHMMSS}`

**Directories:**
- TypeScript packages: `kebab-case` (e.g., `shared`, `extension`, `web`)
- Subdirectories: `kebab-case` (e.g., `hand-collector`, `remote-control`)
- Python: `snake_case` (e.g., `tournament_data`)

## Where to Add New Code

**New poker stat or calculation:**
- Add to: `pokerhud/shared/utils/stats-calculator.ts`
- Add type to: `pokerhud/shared/types/stats.ts` (add to `AggregateStats` interface)
- Tests: `pokerhud/tests/stats.test.ts`

**New web dashboard page:**
- Page component: `pokerhud/web/src/pages/NewPage.tsx`
- Route: Add to `pokerhud/web/src/App.tsx` Routes
- Supporting components: `pokerhud/web/src/components/`

**New content script feature (HUD overlay):**
- Component: `pokerhud/extension/src/content/` (new `.tsx` file)
- Wire into: `pokerhud/extension/src/content/module-manager.tsx` or `index.tsx`

**New background service worker message handler:**
- Add case to switch in: `pokerhud/extension/src/background/index.ts:21`
- Handler function: Same file or new service file in `src/background/`

**New shared utility:**
- Implementation: `pokerhud/shared/utils/new-utility.ts`
- Export from: `pokerhud/shared/index.ts`
- Types: `pokerhud/shared/types/` (new or existing file)

**New Python worker:**
- Create: `workers/worker{N}_{description}.py`
- Follow pattern: DB config dict, logging setup, main function
- Log to: `/opt/pokerhud/logs/worker{N}_{name}.log`

**New Flask API endpoint on Dublin:**
- Add to: `dublin-mirror/plo-w4p/app.py` or create new `{feature}_routes.py`
- Register blueprint in `app.py` using `register_{feature}_routes(app)` pattern

**New Supabase table:**
- Migration: `pokerhud/supabase/migrations/{timestamp}_{description}.sql`
- Types: `pokerhud/shared/types/` (add interface)
- CRUD: `pokerhud/shared/utils/supabase.ts` (add functions)

## Special Directories

**`dublin-mirror/`:**
- Purpose: Local mirror of production Dublin EC2 server code (synced via `sync-from-dublin.sh`)
- Generated: No (manually synced)
- Committed: Yes
- Note: Source of truth is Dublin server. Never push changes to Dublin from here.

**`pokerhud/extension/dist/`:**
- Purpose: Built Chrome extension files (loaded into Chrome)
- Generated: Yes (`npm run build:extension`)
- Committed: Partially (for easy loading)

**`pokerhud/web/dist/`:**
- Purpose: Built web dashboard static files
- Generated: Yes (`npm run build:web`)
- Committed: Partially

**`.venv/` and `venv/`:**
- Purpose: Python virtual environments
- Generated: Yes
- Committed: No (gitignored)

**`pokerhud/node_modules/`:**
- Purpose: npm dependencies
- Generated: Yes
- Committed: No (gitignored)

**`tournament_data/`:**
- Purpose: Output directory for tournament scraper JSON files
- Generated: Yes (by tournament_scraper.py)
- Committed: Selectively

**`logs/`:**
- Purpose: Worker log file output
- Generated: Yes (by workers)
- Committed: No

**`.planning/`:**
- Purpose: Planning and analysis documents for GSD workflow
- Generated: By analysis tools
- Committed: Yes

---

*Structure analysis: 2026-04-29*
