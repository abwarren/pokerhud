# Slices — Harmonization Execution Manifest

Source of truth: `docs/SYSTEM-HARMONIZATION.md`. Each slice is a vertical slice with
evidence + commit. Orchestrator (main session) does destructive ops + integration +
commits. Subagents: file-ownership disjoint, contracts inline, read-only on shared files.

| Slice | Phase | Deliverable | Evidence | Executor |
|-------|-------|-------------|----------|----------|
| 1 | 1 | DB consolidation: drop er_verify_* ×5, retire new_er + sunbet_hands (dump backup first). er_hands stays until Slice 5 | `pg_database` clean; dumps in ~/backups | main loop |
| 2 | 2 | Scraper unification: delete orphaned legacy scrapers; w4p.js config-driven; extension multi-site selector profiles | grep zero refs; `grep -r potlimitomaha\|trk_prod` = 0; extension loads on both hosts | main loop + 2 subagents |
| 3 | 3 | Backend merge: dashboard.py + app.py → one Flask app (blueprints), one port 8899; eval7 in-process; er-engine HTTP hop gone | one process serves both; equity roundtrip local | subagent + main verify |
| 4 | 4 | Tenant hardening: site key on remote state tables; dashboard site filter; selector registry | cross-site bleed test | subagent + main verify |
| 5 | 5 | Decommission: stop er-remote/er-engine containers, archive E-R repo | docker ps clean, ports free | main loop |
| 6 | 6 | SSE push on table state; one page (remote grid + equity panel) | req rate -90% | subagent + main verify |

## Contracts (frozen per slice)

### Slice 2A — w4p.js config-driven (file: `w4p.js` only)
- Top-of-file `CONFIG = { apiBase, apiKey }` defaults; override via `window.W4P_CONFIG`
  if set before inject. apiKey empty → log warn, no API calls. No hardcoded prod key/URL.
- Behavior otherwise identical. Update header comment.

### Slice 2B — extension multi-site (files: `extension/manifest.json`, `extension/src/**`, `extension/dist/**`)
- Profile schema: `{ site, domains[], seatSel, nameSel, stackSel, boardSel, potSel, canvasTable }`
- `evenbet.json`: site=sunbet, domains=[sb-play.pkrsrv.com, sb-web.pkrsrv.com],
  seatSel=.r-seat, nameSel=.player-name, stackSel=.player-cash, boardSel=.r-table-cards .r-card .face,
  potSel=.bank-container-content, canvasTable=false
- `betconstruct.json`: site=pokerbet, domains=[poker-web.pokerbet.co.za, poker-web.goldrush.co.za],
  existing canvas/seat heuristics, canvasTable=true
- content.js: pick profile by hostname; every snapshot gains `site` field; HUD unchanged.
- manifest: matches + host_permissions cover both domain sets. src and dist in sync.
- No API key handling changes (dashboard sync stays localhost:8899).

### Slice 3 — backend merge (files: `app.py`, `dashboard.py`, new `blueprints/` if used)
- One Flask app (app factory or single file), one port (8899). Existing route paths MUST
  not change (dashboard /api/* + remote /api/* + /remote + /api/health).
- eval7 imported in-process; equity endpoint computes locally (no :5002 hop).
- Keep mtt db.py credential pattern (env + ~/.pokerhud_pgpass). No secrets in source.

## Session boundaries
SESSION_HANDOFF.md rewritten after every slice (overwrite, never append).
