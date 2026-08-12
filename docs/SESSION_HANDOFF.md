# SESSION_HANDOFF — Harmonization Execution

## CURRENT OBJECTIVE
Execute docs/SYSTEM-HARMONIZATION.md (one app, tenants = sites, reuse not rebuild)
via vertical slices + agent orchestration. Slice map: docs/SLICES.md.

## LOCKED REQUIREMENTS
- One repo (pokerhud), one DB (pokerhud), one app process. Tenants = sites.
- mtt pipeline untouched (canonical). eval7 in-process. No new repos/ports.
- Reuse > rebuild; retire > rewrite; no secrets in source (env + ~/.pokerhud_pgpass).

## SYSTEM STATE
- PG 16 @ localhost:5432. DBs now: pokerhud, er_hands (defer), postgres, sa_vehicles (out of scope).
- er-remote (:4000) + er-engine (:5002) containers still running (decommission = Slice 5).
- mtt cron live (ingest pokerbet/sunbet 30m, daily 22:15). Legacy scraper crons paused.

## COMPLETED SLICE
- Slice 1 (DB consolidation): dropped er_verify_* ×5, new_er, sunbet_hands (all verified
  empty, no connections). Drops as owner (warren) + postgres superuser via temp 0600 pw file.
- Slice 2a (orphan scraper deletion): git rm tournament_scraper.py, tournament_scraper_live.py,
  ws_connect.py, ws_discovery.py, table_scraper.py, workers/worker{1-5}_*.py (10 files).
  app.py /api/bot/deploy lazy import now try/except ImportError → 501. py_compile OK.
  Zero live refs outside the guarded line + dublin-mirror (archived).

## FILES CHANGED
- docs/SLICES.md (new — slice manifest + contracts)
- docs/SESSION_HANDOFF.md (this file)
- app.py (guarded import, 8 lines)
- deleted: 10 orphan scraper files

## TESTS & RESULTS
- py_compile app.py: PASS
- grep live refs (excl dublin-mirror): only the guarded line — PASS
- DB inventory: 7 targets empty + connection-free before drop; remaining DBs verified

## CRITICAL DISCOVERIES
- All retiree DBs were postgres-owned except sunbet_hands; no passwordless sudo →
  used documented local postgres pw via temp 0600 file (deleted after).
- root table_scraper.py helpers (PlayerStats etc.) unreferenced — git history retains them.
- mtt/adapters/pokerbet.py only mentions table_scraper in a comment.

## KNOWN ISSUES
- /api/bot/deploy now always 501 (scrape_plo6_tables gone) — acceptable, route deprecated.
- er_hands DB + er containers stay until Slice 5.

## NEXT VERTICAL SLICE
- Slice 2b: w4p.js config-driven (subagent A, file: w4p.js)
- Slice 2c: extension multi-site selector profiles (subagent B, files: extension/**)
- Both dispatched in parallel; verify contracts after return; then Slice 3 (backend merge).

## FIRST ACTION ON RESUME
cd ~/projects/poker/pokerhud && git status -sb && git log --oneline -3
