# PokerHUD — Tournament PLO HUD Pipeline (Localhost)

## What This Is

A stable end-to-end HUD pipeline running entirely on localhost. The Chrome extension scrapes real PokerBet PLO tournament table data, POSTs snapshots to a local backend (127.0.0.1:1080), computes player stats, and renders accurate seat-mapped HUD overlays on the live table. Fix the existing system — do not redesign.

## Core Value

Correct data in, correct stats out, correct display rendered. The existing pipeline must work end-to-end locally. Every layer reflects actual table state — no invented data, no approximations.

## Requirements

### Validated

- ✓ Chrome extension infrastructure (Manifest V3, content script, background SW, popup) — existing
- ✓ PokerBet DOM scraping framework (content script injection into iframe) — existing, ~90% correct
- ✓ HUD overlay rendering foundation (extension injects overlay elements) — existing
- ✓ Shared TypeScript library with types and parser — existing
- ✓ Local backend exists (needs validation for HUD flow) — existing

### Active

- [ ] Extension scrapes ALL visible PLO tournament table state from PokerBet DOM
- [ ] Scrapes: all players, names, stacks (numeric), seat position, hero flag, active player, dealer button, pot, board cards, hero cards, action buttons
- [ ] Selectors validated live via querySelectorAll with fallbacks — never hardcoded blindly
- [ ] Scrape frequency: read every 500ms, POST if changed every 1000ms
- [ ] Missing data returns null + warning — never fabricates values
- [ ] Local backend runs on http://127.0.0.1:1080
- [ ] POST /api/hud/snapshot — accepts snapshot JSON, deduplicates
- [ ] GET /api/hud/stats?table_id=... — returns per-player stats
- [ ] GET /api/hud/health — returns {"ok": true}
- [ ] In-memory storage (latest_tables={}, player_stats={}) — no SQL yet
- [ ] Players tracked by: player_name (primary) + table_id + timestamp
- [ ] Stats computed only when reliable: hands, VPIP, PFR, 3BET, AF
- [ ] If action detection unreliable → status: "collecting_data", not fabricated stats
- [ ] HUD overlay renders on correct player seats using boundingClientRect()
- [ ] Overlay does NOT block clicks, updates every 1 second
- [ ] HUD display: PlayerName / VPIP|PFR / 3B|AF / HANDS
- [ ] No data → shows "Collecting..." with H 0
- [ ] window.PBHUD.snapshot() returns current state for console validation

### Out of Scope

- Cash games — tournament only for this milestone
- Dublin as primary backend — localhost only
- Production deployment — local dev machine only
- UI redesign — fix existing overlay, don't redesign
- SQL/Supabase persistence — in-memory until pipeline verified
- New architecture — fix what exists
- WebSocket push — polling/fetch is acceptable

## Context

- **Environment**: Dell local machine, localhost only
- **Backend URL**: http://127.0.0.1:1080
- **PokerBet platform**: Games run inside an iframe (skillgames/18751019). DOM scraped from within iframe context.
- **Current state**: Scraping ~90% correct but unverified. Actions unreliable. Seat mapping unstable. Backend exists but not validated for HUD flow. Overlay exists but not correctly fed.
- **Extension config**: API_BASE=http://127.0.0.1:1080, HUD_MODE=local, HUD_SCOPE=plo_tournaments_only
- **Logging format**: [PBHUD][SCRAPE|POST|HUD|WARN|ERROR] structured prefix logs

## Constraints

- **Environment**: Localhost ONLY — OFFLINE-FIRST. System must work with internet killed.
- **No remote calls**: ZERO calls to potlimitomaha.xyz, Dublin, Supabase, or any remote API in the HUD loop. If existing code references remote endpoints → replace with localhost or gate behind ENV check.
- **Backend binding**: 0.0.0.0:1080, reachable at http://127.0.0.1:1080. Start via `python server.py` or `uvicorn app:app --port 1080`.
- **Approach**: Fix existing system — no redesign, no starting from scratch
- **Storage**: In-memory first — SQL only after pipeline verified end-to-end
- **Data integrity**: Never invent/approximate data. Missing = null + warning.
- **Latency**: HUD overlay updates every 1 second, no blocking clicks
- **Safety**: Backup files before edits. No destructive changes. Feature flags for selector changes.
- **Game type**: PLO tournaments only
- **Verification**: DevTools Network tab must show ALL calls to 127.0.0.1:1080, ZERO to external domains.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Localhost backend (127.0.0.1:1080) | Local dev first, no external dependencies | — Pending |
| In-memory storage first | Fastest path to verified pipeline | — Pending |
| PLO tournaments only | Focused scope, cash games deferred | — Pending |
| Fix existing, don't redesign | Working pieces exist, just need pipeline connected | — Pending |
| 500ms scrape / 1000ms POST | Balance between responsiveness and overhead | — Pending |
| Stats withheld if unreliable | "collecting_data" > fabricated numbers | — Pending |

## Phase Priority (Strict Order)

1. **FIX SCRAPING** — everything depends on this
2. **VALIDATE DATA FLOW** — extension → backend → response
3. **COMPUTE STATS** — basic metrics only when data reliable
4. **RENDER HUD OVERLAY** — seat-mapped display

DO NOT SKIP STEPS.

## Validation Criteria

1. `window.PBHUD.snapshot()` → shows players, stacks, buttons
2. `curl http://127.0.0.1:1080/api/hud/health` → `{"ok": true}`
3. POST snapshot returns `ok:true`
4. HUD appears on ALL players, moves with seats, no click blocking

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone:**
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-29 after initialization*
