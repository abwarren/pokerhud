# Technology Stack

**Analysis Date:** 2026-04-29

## Languages

**Primary:**
- TypeScript 5.9.3 - Chrome extension, web dashboard, shared library (`pokerhud/extension/`, `pokerhud/web/`, `pokerhud/shared/`)
- Python 3.12.3 - Backend services, scrapers, Flask APIs (root-level `*.py`, `workers/`)

**Secondary:**
- JavaScript (ES2020+) - Chrome extension loaders, DOM scrapers (`w4p-extension/loader.js`, `pokerhud/shared/scrapers/pokerbet.js`, `tournament_console_scraper.js`)
- SQL (PostgreSQL 17) - Database schemas and migrations (`supabase/migrations/`)

## Runtime

**Environment:**
- Node.js 18.19.1 (TypeScript/React frontend)
- Python 3.12.3 (Flask backend services)
- Chrome Extension (Manifest V3, service worker)

**Package Manager:**
- npm (Node.js, lockfileVersion 3)
- Lockfile: `pokerhud/package-lock.json` present
- pip (Python venv at `/opt/pokerhud/venv/`)

## Frameworks

**Core:**
- React 18.3.1 - Web dashboard UI and extension popup (`pokerhud/web/`, `pokerhud/extension/src/popup/`)
- Flask 3.1.3 - Python API servers (`snapshot_server.py`, `dashboard.py`, `hud_dashboard.py`)
- Supabase (hosted) - Database, auth, storage (`@supabase/supabase-js` 2.93.3)

**Testing:**
- Jest (configured via `pokerhud/jest.config.js` with ts-jest preset)
- Playwright (referenced in root `package.json` for e2e)

**Build/Dev:**
- Vite 5.4.21 - Build tool for extension and web (`pokerhud/extension/vite.config.ts`, `pokerhud/web/vite.config.ts`)
- TailwindCSS 3.4.19 - Utility-first CSS (`pokerhud/web/tailwind.config.js`, `pokerhud/extension/tailwind.config.js`)
- PostCSS 8.4.32 - CSS processing

## Key Dependencies

**Critical:**
- `@supabase/supabase-js` 2.93.3 - Cloud database, auth, and real-time (all data persistence)
- `react` 18.3.1 - UI framework for extension popup and web dashboard
- `react-router-dom` 6.21.1 - SPA routing in web dashboard
- `psycopg2-binary` 2.9.11 - PostgreSQL driver for Python backend services
- `websockets` 16.0 - WebSocket client for BetConstruct protocol scraping

**Infrastructure:**
- `flask-cors` 6.0.2 - CORS handling for Flask APIs
- `python-socketio` 5.16.1 - Socket.IO support for real-time communication
- `requests` 2.33.1 - HTTP client for REST API scraping
- `beautifulsoup4` 4.14.3 - HTML parsing for scrapers

**Extension-Specific:**
- `@types/chrome` 0.0.260 - Chrome extension API typings
- `@vitejs/plugin-react` 4.2.1 - React JSX transform for Vite builds

## Workspace Architecture

**Monorepo (npm workspaces):**
- Root: `pokerhud/package.json`
- `pokerhud/extension/` - Chrome extension (Manifest V3)
- `pokerhud/web/` - Web dashboard (React SPA)
- `pokerhud/shared/` - Shared library (types, utils, Supabase client, OpenRouter AI client)

## Configuration

**TypeScript:**
- Target: ES2020
- Module: ESNext with bundler resolution
- Strict mode enabled (`strict: true`)
- Path alias: `@shared` maps to `../shared`
- JSX: react-jsx

**Build:**
- `pokerhud/web/vite.config.ts` - Web dashboard build
- `pokerhud/extension/vite.config.ts` - Extension build with custom IIFE bundling for content scripts
- `pokerhud/web/tailwind.config.js` - Tailwind configuration
- `pokerhud/vercel.json` - Vercel deployment config for web dashboard

**Environment Variables:**
- `.env` file present (not read - contains secrets)
- `VITE_SUPABASE_URL` - Supabase project URL
- `VITE_SUPABASE_ANON_KEY` - Supabase anon key
- `VITE_OPENROUTER_API_KEY` - OpenRouter AI API key
- `VITE_OPENROUTER_MODEL` - AI model selection
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` - Local PostgreSQL connection
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase admin key (Python workers)

## Platform Requirements

**Development:**
- Node.js 18+ (ES module support required)
- Python 3.12+ with venv
- PostgreSQL 17 (local dev via Supabase CLI or direct)
- Chrome browser (extension testing)

**Production:**
- Vercel (web dashboard hosting, configured in `pokerhud/vercel.json`)
- Supabase Cloud (PostgreSQL 17, Auth, Storage) - Project: `kzqrdtagpykoylhuqcyv`
- EC2 Dublin (52.16.14.220) - Flask APIs, Python workers
- Chrome Extension (distributed separately)

---

*Stack analysis: 2026-04-29*
