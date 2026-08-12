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
- er-remote (:4000) + er-engine (:5002) containers still running (decommission = Slice 5).
- mtt cron live (ingest pokerbet/sunbet 30m, daily 22:15). Legacy scraper crons paused.

## COMPLETED SLICES
- Slice 1 (DB consolidation): dropped er_verify_* ×5, new_er, sunbet_hands (empty, no conns).
- Slice 2a (orphan scraper deletion): git rm 10 files; app.py /api/bot/deploy import guarded → 501.
- Slice 2b (w4p.js config-driven): CONFIG defaults + window.W4P_CONFIG override, no secrets in
  source. Subagent A verified 24/24 (ad-hoc). Committed f242d3c.
- Slice 2c (extension multi-site): selector profiles evenbet.json/betconstruct.json, hostname
  profile switch, site-tagged snapshots, SunBet host perms. Subagent B + manual file review.
  Committed e922805.

## FILES CHANGED (this session)
- docs/SLICES.md, docs/SESSION_HANDOFF.md (new)
- app.py (guarded import), w4p.js (config-driven)
- extension/: manifest.json, src/content/content.js (multi-site), src/selectors/{evenbet,betconstruct}.json,
  src/** mirrored to dist/**
- deleted: tournament_scraper.py, tournament_scraper_live.py, ws_connect.py, ws_discovery.py,
  table_scraper.py, workers/worker{1-5}_*.py

## TESTS & RESULTS
- py_compile app.py: PASS; node -c w4p.js: PASS (subagent, 24/24 ad-hoc checks)
- Extension files reviewed manually per contract (profiles/manifest/content.js)
- DB drops: verified empty + connection-free before drop; remaining DBs confirmed

## CRITICAL DISCOVERIES
- Subagent sandbox can't rm /tmp files (guard denies) — clean up leftovers in main loop.
- Python 3.12 raises ModuleNotFoundError (ImportError subclass) — match on type, not string.
- dashboard.py (:8899) and app.py (:4000 heritage) both define module-level Flask `app` —
  merge needs blueprint extraction or DispatcherMiddleware; both must serve from ONE port (8899).

## KNOWN ISSUES
- /api/bot/deploy now always 501 (legacy scraper gone) — acceptable, route deprecated.
- SunBet board cards are SVG-background faces — board stays [] until SVG fingerprinting.
- er_hands DB + er containers stay until Slice 5.

## NEXT VERTICAL SLICE
- Slice 3: backend merge. dashboard.py + app.py → one process/one port (8899); eval7 in-process
  (no :5002 hop). Analysis subagent dispatched (read-only → merge plan); main loop executes.

## FIRST ACTION ON RESUME
cd ~/projects/poker/pokerhud && git status -sb && git log --oneline -3
