# External Integrations

**Analysis Date:** 2026-04-29

## APIs & External Services

**Supabase (Primary Database & Auth):**
- Project URL: `https://kzqrdtagpykoylhuqcyv.supabase.co`
- SDK/Client: `@supabase/supabase-js` ^2.39.3 (installed 2.93.3)
- Python client: `supabase` package (used in `workers/worker5_timeseries_ledger.py`)
- Auth: `VITE_SUPABASE_ANON_KEY` (frontend), `SUPABASE_SERVICE_ROLE_KEY` (backend workers)
- Usage: User data, game history, player stats, hands, unified players, aliases, notes, live games, player timeseries
- Client initialization: `pokerhud/shared/utils/supabase.ts`
- Tables: users, games, hands, unified_players, player_stats, player_aliases, player_notes, import_logs, live_games, player_timeseries
- Migrations: `pokerhud/supabase/migrations/` (8 migration files)
- RLS: Enabled via migration `20260201000001_enable_rls.sql`

**OpenRouter (AI/LLM Service):**
- Base URL: `https://openrouter.ai/api/v1/chat/completions`
- Model: `anthropic/claude-opus-4.5` (configurable via `VITE_OPENROUTER_MODEL`)
- Auth: `VITE_OPENROUTER_API_KEY` (Bearer token)
- Usage: Player exploitative analysis, real-time hand advice
- Client: `pokerhud/shared/utils/openrouter.ts` (OpenRouterClient class)
- Features: Player type classification, exploitative takeaways, hand advice (fold/call/raise recommendations)
- Headers: `HTTP-Referer: https://pokerbet-hud.com`, `X-Title: PokerBet HUD`

**BetConstruct Skillgames Platform (Poker Backend):**
- WebSocket: `wss://poker-general.skillgames-bc.com` (live lobby data, custom backslash-delimited protocol)
- WebSocket Alt: `wss://web.skillgames-bc.com:8443`
- Gateway REST: `https://sg-api.skillgames-bc.com/` (player notes, session data)
- CMS: `https://go-cms.pokerbet.co.za/` (promotions, banners, game catalog)
- Hands: `https://poker-hands.skillgames-bc.com` (hand history)
- Promotions: `https://poker-promotions.skillgames-bc.com` (bonuses)
- Rates: `https://poker-rate.skillgames-bc.com/api/rate` (currency ZAR/EUR)
- Client config: `https://poker-web.pokerbet.co.za/18751019/config.json`
- Partner ID: `18751019`
- Product ID: `3` (poker)
- Package ID: `4349`
- Usage: Tournament scraping, lobby data, cash game monitoring
- Files: `tournament_scraper.py`, `ws_connect.py`, `ws_discovery.py`, `workers/worker1_lobby_scraper.py`

**PokerBet.co.za (Poker Site - DOM Scraping Target):**
- Main URL: `https://pokerbet.co.za`
- Poker client: `https://poker-web.pokerbet.co.za`
- Iframe games: `https://*.skillgames-bc.com/*`
- Auth: Session-based (browser cookies, client_id, token)
- Usage: Live table state scraping via Chrome extension content scripts
- DOM selectors: `pokerhud/extension/src/content/pokerbet-observer.ts`
- Content scripts inject into: `pokerbet.co.za`, `skillgames-bc.com`

**PokerNow.club (Secondary Poker Site):**
- URLs: `https://*.pokernow.club/games/*`, `https://*.pokernow.com/games/*`
- Usage: Alternative site support for HUD overlay
- Observer: `pokerhud/extension/src/content/pokernow-observer.ts`
- Parser: CSV log format parsing (`pokerhud/shared/utils/parser.ts`)

**W4P Remote Control (potlimitomaha.xyz):**
- Server: `https://potlimitomaha.xyz`
- Fetched resource: `/w4p.js` (injected into poker table pages)
- Extension: `w4p-extension/loader.js` - fetches and injects w4p.js into matching pages
- Purpose: Remote table control for PLO bot automation

## Data Storage

**Databases:**
- Supabase Cloud (PostgreSQL 17) - Primary production database
  - Connection: `VITE_SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`
  - Client: `@supabase/supabase-js` (TypeScript), `supabase` Python package
  - Schema: See `supabase/migrations/20260413150000_hud_initial_schema.sql`

- Local PostgreSQL - Secondary/development
  - Connection: `localhost:5432`, database `pokerhud`
  - Client: `psycopg2-binary` (Python)
  - Tables: `myplayerspokerbet`, `cash_balances` (player ledger tracking)
  - Used by: `dashboard.py`, `hud_dashboard.py`, `workers/worker1_lobby_scraper.py`

**File Storage:**
- Local filesystem (`/opt/pokerhud/snapshots/`) - Snapshot JSON files
- Local filesystem (`/opt/pokerhud/tournament_data/`) - Tournament scrape results
- Local filesystem (`/opt/pokerhud/logs/`) - Worker log files
- `chrome.storage` - Extension local data (auth state, settings)

**Caching:**
- Supabase `player_stats_cache` table (lobby-scraped player data)
- In-memory (Python Flask apps - no external cache layer)
- `chrome.storage.local` (extension-side caching)

## Authentication & Identity

**App Auth (Supabase):**
- Custom password-hash based auth (not Supabase Auth)
- Implementation: `pokerhud/shared/utils/auth.ts`
- Storage: `users` table with `password_hash` + optional `device_id`
- No email/OAuth - simple hash-based user identification

**BetConstruct Platform Auth:**
- Token-based: `CLIENT_ID`, `CLIENT_ID_HASH`, `PLAYER_ID`, `TOKEN`
- Session-specific tokens from network trace
- Used in REST headers and WebSocket handshake

## Monitoring & Observability

**Error Tracking:**
- None (console.error only)

**Logs:**
- Python: `logging` module to stdout + file (`/opt/pokerhud/logs/`)
- TypeScript: `console.log`/`console.error`
- Worker logs: `/opt/pokerhud/logs/worker1_lobby.log`
- Scraper logs: `/opt/pokerhud/tournament_data/scraper.log`

## CI/CD & Deployment

**Web Dashboard Hosting:**
- Vercel (configured in `pokerhud/vercel.json`)
- Build: `npm run build:web` -> output `web/dist/`
- SPA rewrites enabled

**Flask APIs:**
- EC2 Dublin (52.16.14.220) - manual deployment
- Python venv at `/opt/pokerhud/venv/`
- Snapshot server: port 8888
- Dashboard: port 8899
- HUD dashboard: port from env

**Chrome Extension:**
- Manual build via `npm run build:extension`
- Output: `pokerhud/extension/dist/`
- Distributed as unpacked extension or zip

**CI Pipeline:**
- None detected (no GitHub Actions, no CI config files)

## Environment Configuration

**Required env vars (TypeScript/Frontend):**
- `VITE_SUPABASE_URL` - Supabase project URL
- `VITE_SUPABASE_ANON_KEY` - Supabase anonymous key
- `VITE_OPENROUTER_API_KEY` - OpenRouter LLM API key
- `VITE_OPENROUTER_MODEL` - LLM model identifier

**Required env vars (Python/Backend):**
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` - PostgreSQL connection
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key (admin access)

**Secrets location:**
- `.env` file at project root (exists, not committed)
- Hardcoded fallbacks in `pokerhud/shared/utils/supabase.ts` and `pokerhud/shared/utils/openrouter.ts` (dev convenience)
- Worker files contain inline credentials for local PostgreSQL (`workers/worker1_lobby_scraper.py`)

## Webhooks & Callbacks

**Incoming:**
- `POST /api/snapshot` on port 8888 - Receives Chrome extension table state snapshots (`snapshot_server.py`)

**Outgoing:**
- OpenRouter API calls for AI analysis (`pokerhud/shared/utils/openrouter.ts`)
- BetConstruct REST API calls for tournament/lobby data (`tournament_scraper.py`)
- BetConstruct WebSocket connections for live data (`ws_connect.py`)

## External Libraries (Notable)

**Chart.js 4.4.1:**
- Loaded via CDN in `dashboard.py` inline HTML
- Used for: Player balance time-series charts, P&L visualization
- Adapter: `chartjs-adapter-date-fns` 3.0.0

**GTO Ranges Data:**
- Static JSON: `pokerhud/shared/constants/gto-ranges.json`
- Used by: `pokerhud/shared/utils/hand-advisor.ts` for rule-based hand advice

---

*Integration audit: 2026-04-29*
