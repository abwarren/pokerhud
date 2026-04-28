# Codebase Concerns

**Analysis Date:** 2026-04-29

## Tech Debt

**Monolithic Flask Application (2442 lines):**
- Issue: `dublin-mirror/plo-w4p/app.py` is a 2442-line single file handling authentication, table state, commands, collector, cashout, GoldRush, player management, batch parsing, poker table CRUD, and graceful shutdown — all in one module.
- Files: `dublin-mirror/plo-w4p/app.py`
- Impact: Extremely difficult to test in isolation, any change risks regressions across unrelated features. Import ordering issues (e.g., `import re as _re` at line 1796, `import signal` at line 1981 long after main code).
- Fix approach: Extract into route blueprints: `snapshot_routes.py`, `collector_routes.py`, `cashout_routes.py`, `goldrush_routes.py`, `poker_tables_routes.py`, `player_routes.py`. Keep `app.py` as the composition root only.

**Duplicate Codebases (plo-w4p vs plo-test-engine):**
- Issue: `dublin-mirror/plo-test-engine/app.py` (1522 lines) replicates large portions of `dublin-mirror/plo-w4p/app.py` with slight modifications (same HMAC logic, same state management, same API patterns).
- Files: `dublin-mirror/plo-test-engine/app.py`, `dublin-mirror/plo-w4p/app.py`
- Impact: Bug fixes must be applied to both files. Divergence leads to production vs test behavior differences.
- Fix approach: Extract shared logic into a common library imported by both apps.

**Duplicate Static Assets:**
- Issue: Multiple copies of the same JS files across directories with minor version differences.
- Files: `dublin-mirror/plo-engine-static/w4p.js`, `dublin-mirror/plo-w4p/static/w4p.js`, `dublin-mirror/plo-w4p/w4p.js` (899 lines vs 1214 lines vs 1365 lines)
- Impact: Unclear which is authoritative. Stale copies may be served if nginx routes change.
- Fix approach: Single source of truth for each JS asset. Use symlinks or build step to distribute.

**Backup Files Committed to Repo:**
- Issue: Backup and snapshot files are versioned in the repository.
- Files: `dublin-mirror/plo-w4p/static/n4p_v2_backup_20260324_171313.js`, `dublin-mirror/plo-w4p/static/remote_grid_backup_20260324_153519.html`, `dublin-mirror/plo-w4p/static/n4p.js.backup_full_table`, `dublin-mirror/plo-w4p/static/index.html.working_backup`
- Impact: Bloats repository, confuses which files are active, risk of accidentally serving backup files.
- Fix approach: Remove backup files from repo. Add `*.backup*`, `*_backup_*` to `.gitignore`.

**BLM Engine (unrelated domain) in poker codebase:**
- Issue: `blm_engine.py` (1614 lines) is a Basketball League Manager engine with NBA stats, three-point tracking, hot score calculations — completely unrelated to poker.
- Files: `blm_engine.py`, `nba_sync.py`, `dublin-mirror/plo-w4p/blm_routes.py`, `dublin-mirror/plo-w4p/blm_database.py`
- Impact: Muddies the repository purpose, increases cognitive load, routes registered in the poker Flask app.
- Fix approach: Move to separate repository or at minimum a clearly isolated subdirectory with its own deployment.

**In-Memory State with Single Lock:**
- Issue: All table state, command queues, cashout state, bot mappings, and hand history stored in Python dicts protected by a single `_store_lock` threading lock.
- Files: `dublin-mirror/plo-w4p/app.py` (lines 157-171)
- Impact: Lock contention under load. State lost on crash despite periodic disk persistence (10s window). No horizontal scaling possible.
- Fix approach: Move state to Redis or SQLite with WAL mode for durability. Use per-table locks to reduce contention.

## Known Bugs

**Bare except silencing errors:**
- Symptoms: Database insert failures silently ignored, making debugging impossible.
- Files: `dublin-mirror/plo-w4p/cb2k_v2.py:231` (`except: pass`), `ws_discovery.py:381` (`except:`)
- Trigger: Any database constraint violation or unexpected data format.
- Workaround: None; errors are silently swallowed.

**HMAC function name typo (potential):**
- Symptoms: `hmac.new()` should be `hmac.HMAC()` or the module-level `hmac.new()` function.
- Files: `dublin-mirror/plo-w4p/app.py:299`
- Trigger: If Python version uses uppercase HMAC. In practice `hmac.new` works as an alias in CPython but is undocumented.
- Workaround: Currently works but may break on future Python versions.

## Security Considerations

**Hardcoded API Keys and Supabase Tokens in Source:**
- Risk: Service role keys (full database access) committed to git in plaintext. Anyone with repo access gains full Supabase admin access.
- Files: `workers/worker5_timeseries_ledger.py:19` (service_role key), `pokerhud/shared/utils/supabase.ts:14` (anon key), `tournament_scraper_live.py:28` (anon key), `nba_sync.py:14` (service key), `blm_engine.py:40` (service key), `pokerhud/shared/utils/openrouter.ts:3` (OpenRouter API key)
- Current mitigation: `.env` files exist and are gitignored, but fallback defaults contain real keys.
- Recommendations: Remove all hardcoded keys. Use environment variables exclusively with no default fallback values. Rotate all exposed keys immediately.

**Plaintext Player Passwords in Database:**
- Risk: Player credentials stored as plaintext in SQLite `players` table (not hashed). API endpoint returns passwords in GET response.
- Files: `dublin-mirror/plo-w4p/app.py:1721` (SELECT password), `dublin-mirror/plo-w4p/api.py:51-52` (UPDATE with raw password), `dublin-mirror/plo-w4p/database.py:33` (schema: `password TEXT NOT NULL`)
- Current mitigation: None. The user auth system (users table) uses proper `werkzeug` password hashing, but the player/bot credentials do not.
- Recommendations: These are poker site credentials used for bot login — they need to be stored reversibly (not hashed) but should be encrypted at rest.

**Weak API Key Authentication:**
- Risk: Static API keys with no rotation mechanism. Default key `'default_secret_change_me'` as HMAC secret. Multiple "valid" keys accepted including weak defaults.
- Files: `dublin-mirror/plo-w4p/app.py:145-146` (N4P_SEAT_SECRET default, TRACKER_API_KEY), `dublin-mirror/plo-w4p/app.py:618` (valid_keys set includes 'trk_default', 'trk_w4p_default'), `dublin-mirror/plo-w4p/windows_routes.py:29` (`API_KEY = 'n4p-windows-mgmt-2026'`)
- Current mitigation: Rate limiting via flask-limiter.
- Recommendations: Remove default/weak keys. Implement key rotation. Use proper auth tokens with expiration.

**CORS Set to Wildcard:**
- Risk: `CORS(app, origins=r".*")` accepts requests from any origin. Combined with cookie-based auth, this enables CSRF-like attacks.
- Files: `dublin-mirror/plo-w4p/app.py:32`
- Current mitigation: API-key authentication on data endpoints partially mitigates.
- Recommendations: Restrict origins to known domains (potlimitomaha.xyz, pokerbet.co.za).

**Subprocess Execution from User Input (indirect):**
- Risk: Equity routes execute subprocess with file paths derived from user-supplied variant parameter. While the variant is validated against VARIANT_CONFIG, the path construction uses string concatenation.
- Files: `dublin-mirror/plo-w4p/equity_routes.py:96-117`
- Current mitigation: Variant is validated against a fixed dict. script_path checked with `.exists()`.
- Recommendations: No immediate exploit vector, but add explicit path traversal check.

**EC2 Instance IDs Hardcoded:**
- Risk: AWS instance IDs committed to repo, enabling targeted attacks if combined with credential leak.
- Files: `dublin-mirror/plo-w4p/windows_routes.py:16-24`
- Current mitigation: API key required for management endpoints.
- Recommendations: Move to environment config or AWS parameter store.

## Performance Bottlenecks

**Single-Threaded State Lock:**
- Problem: All snapshot POSTs, command polls, and table reads contend for the same `_store_lock`.
- Files: `dublin-mirror/plo-w4p/app.py:167` (_store_lock), used in snapshot (line 642), commands (line ~900+), cleanup (line 561)
- Cause: Threading.Lock is not granular — 9 bots sending snapshots at 300ms intervals all compete.
- Improvement path: Per-table locking (dict of locks keyed by table_id) or async framework (FastAPI/Quart).

**File-System Polling for Collector Data:**
- Problem: `_sync_collector_batch_to_table()` and `_get_latest_collector_batch()` scan directory with `glob('*.txt')` and `stat()` on every call.
- Files: `dublin-mirror/plo-w4p/app.py:403-438`
- Cause: No event-driven notification; relies on filesystem polling to find newest file.
- Improvement path: Use inotify/watchdog or switch to in-memory writes from the scraper process directly.

**Dashboard DB Queries Without Connection Pooling:**
- Problem: Both `dashboard.py` and `hud_dashboard.py` open/close PostgreSQL connections on every HTTP request.
- Files: `dashboard.py:17` (`psycopg2.connect(**DB)`), `hud_dashboard.py:30` (same pattern)
- Cause: No connection pooler. Each request incurs TCP + auth overhead.
- Improvement path: Use `psycopg2.pool.ThreadedConnectionPool` or connection middleware.

## Fragile Areas

**w4p.js DOM Scraping:**
- Files: `dublin-mirror/plo-w4p/static/w4p.js`, `pokerhud/extension/src/content/pokerbet-observer.ts`, `pokerhud/extension/src/content/index.tsx`
- Why fragile: Relies on exact CSS class names from PokerBet/BetConstruct DOM (`.control-b-view-p.fold-c`, `.player-mini-container-p`, `icon-layer2_{suit}{rank}_p-c-d`). Any poker site frontend update breaks all scraping.
- Safe modification: Always test against live DOM snapshot. Keep selector constants centralized (see `POKERBET_SELECTORS` object in pokerbet-observer.ts lines 10-56).
- Test coverage: No automated DOM tests — relies entirely on manual verification against live site.

**Multi-Bot Seat Synchronization:**
- Files: `dublin-mirror/plo-w4p/app.py` (lines 322-401: `update_bot_seat_mapping`, `clear_bot_seat`, `_build_seats_list`)
- Why fragile: Complex bidirectional mapping between `_bot_seats` (bot_id → seat info) and `_seat_bots` (seat_key → bot_id). Race conditions possible if two bots claim same seat simultaneously.
- Safe modification: Always test with multiple containers sending concurrent snapshots.
- Test coverage: Zero automated tests.

**Hand Key / Hand Reset Logic:**
- Files: `dublin-mirror/plo-w4p/app.py:279-294` (`make_hand_key`), lines 648-675 (hand reset block)
- Why fragile: Uses board cards as hand identifier (no hand number from PokerBet). Two consecutive preflop folds would share the same hand_key. Comment on line 280 explains a previous bug with dealer_seat causing false resets.
- Safe modification: Any change to hand detection requires testing with multi-bot concurrent snapshots.
- Test coverage: None.

## Scaling Limits

**In-Memory State Storage:**
- Current capacity: 9 bots, 1-3 tables.
- Limit: Memory grows linearly with tables/seats. No eviction beyond TTL-based cleanup. At ~100 concurrent tables, dict operations + lock contention would degrade.
- Scaling path: Redis for state, or restructure as async workers per table.

**SQLite for Player Database:**
- Current capacity: 9 players, low write frequency.
- Limit: SQLite does not support concurrent writes. Under heavy API usage, `database is locked` errors will occur.
- Scaling path: Migrate to PostgreSQL (already used for HUD stats) or use WAL mode.

## Dependencies at Risk

**Supabase Anon Key Expiration:**
- Risk: JWT tokens in source have expiration dates embedded (`"exp":2091649104` — year 2036). If Supabase project is recreated or keys rotated, all hardcoded tokens fail silently.
- Impact: All timeseries recording, tournament scraping, and extension Supabase queries break.
- Migration plan: Centralize all Supabase config in environment variables.

**PokerBet/BetConstruct DOM Stability:**
- Risk: Entire system depends on third-party poker site DOM structure remaining unchanged.
- Impact: Any frontend update breaks scraping, command execution, and HUD overlay.
- Migration plan: DOM selector versioning system with automated health checks that alert on selector failures.

## Missing Critical Features

**No Automated Tests for Core Backend:**
- Problem: `dublin-mirror/plo-w4p/` has zero unit tests. The only test files are for the pokerhud extension parser (`pokerhud/tests/parser.test.ts`, `pokerhud/tests/stats.test.ts`).
- Blocks: Safe refactoring of the 2442-line app.py, CI/CD confidence, regression prevention.

**No Health Check Endpoint:**
- Problem: No `/health` or `/readiness` endpoint for the Flask app to verify all subsystems (DB connectivity, state integrity, background threads alive).
- Blocks: Reliable monitoring, automated restart on degradation.

**No Request Validation Layer:**
- Problem: JSON payloads from POST endpoints are consumed with minimal validation. No schema validation (e.g., pydantic, marshmallow, or jsonschema).
- Blocks: Graceful error handling, API documentation, defense against malformed input.

## Test Coverage Gaps

**Backend API Routes (0% coverage):**
- What's not tested: All Flask routes in `dublin-mirror/plo-w4p/app.py` — snapshot ingestion, command queuing, cashout, player management, auth, GoldRush.
- Files: `dublin-mirror/plo-w4p/app.py`, `dublin-mirror/plo-w4p/equity_routes.py`, `dublin-mirror/plo-w4p/auth_routes.py`
- Risk: Any change to snapshot format, hand detection, or command routing can break production with zero warning.
- Priority: High

**Extension Content Scripts (0% coverage):**
- What's not tested: DOM observation, card parsing, seat scraping, action button detection, iframe handling.
- Files: `pokerhud/extension/src/content/pokerbet-observer.ts`, `pokerhud/extension/src/content/index.tsx`
- Risk: Card parsing bugs produce incorrect equity calculations downstream.
- Priority: High

**Worker Scripts (0% coverage):**
- What's not tested: Lobby scraping, active tracking, results collection, timeseries recording.
- Files: `workers/worker1_lobby_scraper.py`, `workers/worker2_active_tracker.py`, `workers/worker3_results_collector.py`, `workers/worker4_icm_snapshots.py`, `workers/worker5_timeseries_ledger.py`
- Risk: Silent data loss or corruption in player tracking pipeline.
- Priority: Medium

**Equity Engine Integration (0% coverage):**
- What's not tested: Hand parsing, subprocess execution, result parsing, error handling for engine failures.
- Files: `dublin-mirror/plo-w4p/equity_routes.py`
- Risk: Incorrect equity percentages displayed to user, wrong decisions.
- Priority: Medium

## Code Quality Issues

**Excessive use of `any` type in TypeScript:**
- Issue: 40+ instances of `as any` type assertions in extension source, particularly in `background/index.ts` (20+ occurrences) and `content/stat-modal.tsx` (12 occurrences).
- Files: `pokerhud/extension/src/background/index.ts`, `pokerhud/extension/src/content/stat-modal.tsx`, `pokerhud/extension/src/content/floating-module.tsx`
- Impact: Type safety bypassed, runtime errors not caught at compile time.
- Fix approach: Define proper interfaces for API responses, DOM event payloads, and stat objects.

**107 console.log statements in extension:**
- Issue: Heavy logging in production content scripts and background workers.
- Files: All files in `pokerhud/extension/src/` (107 total occurrences across 13 files)
- Impact: Performance overhead in tight DOM observation loops. Leaks internal state to browser console where other extensions or users can inspect.
- Fix approach: Implement log-level system (DEBUG/INFO/WARN only in dev builds).

**Hardcoded Database Password in Source:**
- Issue: `dashboard.py` contains plaintext database credentials directly in source.
- Files: `dashboard.py:14` (`password='pokerhud'`), `hud_dashboard.py:26` (`password=os.environ.get('DB_PASS', 'hudpass123')`)
- Impact: Anyone with repo access can connect to PostgreSQL.
- Fix approach: Use environment variables exclusively with no default values containing real credentials.

---

*Concerns audit: 2026-04-29*
