# SESSION_HANDOFF — Harmonization Execution

## CURRENT OBJECTIVE
Execute docs/SYSTEM-HARMONIZATION.md (one app, tenants = sites, reuse not rebuild)
via vertical slices + agent orchestration. Slice map: docs/SLICES.md.

## LOCKED REQUIREMENTS
- One repo (pokerhud), one DB (pokerhud), one app process. Tenants = sites.
- mtt pipeline untouched (canonical). eval7 in-process. No new repos/ports.
- Reuse > rebuild; retire > rewrite; no secrets in source (env + ~/.pokerhud_pgpass).

## SYSTEM STATE
- PG 16 @ localhost:5432. DBs: pokerhud, er_hands (defer), postgres, sa_vehicles (out of scope).
- er-remote (:4000) + er-engine (:5002) containers STILL RUNNING — Slice 5 deferred:
  user denied `docker compose down` (2026-08-12, session). Containers stay until
  explicit approval. gh auth broken (keyring) — repo archiving = docs commit, not GitHub flag.
- mtt cron live (ingest pokerbet/sunbet 30m, daily 22:15). Legacy scraper crons paused.

## COMPLETED SLICES
- Slice 1 (DB consolidation): dropped er_verify_* ×5, new_er, sunbet_hands.
- Slice 2a (orphan scraper deletion): git rm 10 files; /api/bot/deploy guarded → 501.
- Slice 2b (w4p.js config-driven): CONFIG defaults + window.W4P_CONFIG, no secrets. f242d3c.
- Slice 2c (extension multi-site): evenbet/betconstruct profiles, hostname switch, site-tagged
  snapshots. e922805.
- Slice 3 (backend merge): ONE Flask app (webapp package, dashboard+remote+equity blueprints),
  port 8899, eval7 in-process. 7969609. **Blocker fixed this session**: equity "bad card: 'Ah'"
  was NOT an eval7 build issue — it was a lazy-import scope bug (eval7 imported inside equity()
  but used in _parse_card/_best → NameError swallowed into EquityError). Fixed with guarded
  module-level import; 6 regression tests. f301246. Live: /api/equity roundtrip 43ms.
- Slice 4 (tenant hardening): remote state keyed (site, table_id); seat tokens HMAC(site:table_id:seat_no);
  site-scoped _seat_bots/_hero_cards/_bot_actions/_bot_buttons/_command_queue; persistence
  'site::table_id' keys (legacy rows ignored); dashboard ?site= filter (parameterized); selector
  registry (webapp/selector_registry.py, startup validation + GET /api/selectors/status);
  cross-site bleed tests. 28566a2. 100/100 tests green. Live loopback verified both sites
  coexist on same table_id.

## FILES CHANGED (this session)
- webapp/equity.py (eval7 module-level guarded import), tests/test_equity.py (new, 6 tests)
- webapp/remote_bp.py (site tenancy across stores + all route call sites), tests/test_tenant.py (new, 3)
- webapp/dashboard_bp.py (site filter), webapp/selector_registry.py + tests/test_selector_registry.py (new, 5)
- webapp/__init__.py (registry wiring + /api/selectors/status route)
- docs/SESSION_HANDOFF.md (this file)

## TESTS & RESULTS
- Full suite: 100 passed (85 mtt + 6 equity + 5 selector registry + 3 tenant + 1 e2e), 2 warnings.
- Live loopback (:8899, TRACKER_API_KEY=test123 N4P_SEAT_SECRET=devsecret):
  health 200; engine healthy in-process; selectors ok; equity 200; snapshots pokerbet+sunbet
  both 200; /api/tables lists both (site, T1) entries — no collision.

## CRITICAL DISCOVERIES
- eval7 "bad card" blocker root cause = lazy-import scope (see Slice 3).
- Full-suite tenant failures were env-timing: remote_bp caches TRACKER_API_KEY at import;
  earlier test modules import webapp first. Fix = module-global patch fixture, not env setdefault.
- selector_registry.load_profiles must coerce str → Path (caught by ad-hoc verify script).
- Subagent 1 (4a) updated the store layer but missed ~25 route-layer call sites; a focused
  fix subagent completed them. ALWAYS grep call sites of changed signatures after subagent edits.

## KNOWN ISSUES
- /api/bot/deploy always 501 (legacy scraper gone) — acceptable.
- SunBet board cards SVG-background — board stays [] until SVG fingerprinting.
- er_hands DB + er containers stay until Slice 5 (blocked on user approval).
- Live app is running with DEV key (test123) — production deploy must set TRACKER_API_KEY +
  N4P_SEAT_SECRET from env (config defaults empty).

## NEXT VERTICAL SLICE
- Slice 6 (Phase 6 — Efficiency): SSE push on table state (replaces /api/table/latest polling;
  reuse legacy unified-frontend analysis), then one page (remote grid + equity panel).
  Evidence: request rate per UI drops ≥90%.

## FIRST ACTION ON RESUME
cd ~/projects/poker/pokerhud && git status -sb && git log --oneline -3 && ss -tlnp | grep ':8899'
