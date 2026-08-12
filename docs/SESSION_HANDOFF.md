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
- Slice 6 (SSE push): /api/events stream (bounded maxsize-1 queues, drop-old, 15s heartbeat,
  initial-state frame); _notify_sse() on snapshot + command-queue mutations; remote-w4p.html
  EventSource with polling fallback (sseLive flag), site-aware sendCmd. 4fc291f. 102/102 tests.
  Live verified: initial frame + mutation push over HTTP.
- Slice 7 (auto-actions, PLAN TB-004): webapp/auto_actions.py pure engine (cf/cc/kh + off);
  per-table rules via GET/PUT /api/auto-rules (persisted in state file under _auto_rules);
  trigger in post_snapshot on hero turn queues command (source=auto, no-duplicate guard);
  header selector in remote UI. 58c7dac. 113/113 tests. Live TB-004 verified.
- Slice 8 (one-page UI): equity panel merged into remote grid — auto-computes via /api/equity
  on hand/board change (variant map plo→plo4; exact when board complete, else sampled 20K);
  fixed multi-hero hole-card cache bug (last hero got first hero's cards → dup card error);
  +regression test. 7973e7d. 114/114 tests. Browser-verified: panel shows hero1 48.31/hero2 51.69.

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
- All PLAN.md slices delivered (1-5 equivalents + auto-actions + one-page UI + SSE).
  Remaining harmonization: Phase 5 decommission (er containers — BLOCKED on user approval),
  Phase 6 tail (SSE for dashboard? not required). Optional: exact-equity for <5-card boards
  (currently sampled 20K); SVG board fingerprinting for SunBet.

## FIRST ACTION ON RESUME
cd ~/projects/poker/pokerhud && git status -sb && git log --oneline -3 && ss -tlnp | grep ':8899'
