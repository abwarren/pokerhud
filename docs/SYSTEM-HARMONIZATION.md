# System Harmonization Strategy — One App, Tenants = Sites, Reuse Not Rebuild

**Date:** 2026-08-12
**Scope:** The poker platform cluster — pokerhud, E-R (legacy), NEW_E-R (plan).
**Out of scope (separate products, shared conventions only):** BLM (:2262), RoulCollector (:4480),
LivePokerOPS (:8000), voiprct, sa_vehicles.
**Principle (user directive):** one application, different tenants (poker sites). Separation of
topics. **Do NOT rebuild what already exists.**

---

## 1. Current Landscape (inventory)

| Asset | Where | Status | Role |
|-------|-------|--------|------|
| mtt pipeline | pokerhud/mtt/ (2,781 LOC, 85 tests) | ✅ canonical, cron 30m + 22:15 | Tournament data engine: per-site adapters, idempotent PG ingestion |
| mtt adapters | pokerhud/mtt/adapters/{pokerbet,sunbet}.py | ✅ live | Per-site (tenant) scrape profiles — BetConstruct + EvenBet |
| Dashboard | pokerhud/dashboard.py (:8899 Flask) | ⚠️ exists, not running | MTT schedule + player stats UI |
| HUD extension | pokerhud/extension/ (MV3) | ⚠️ PokerBet-only | Table scraper + StatsEngine overlay |
| Remote-control backend | pokerhud/app.py (94 KB Flask v3) | ⚠️ 3rd lineage copy | E&R remote table control (snapshot/commands/equity) |
| w4p.js scraper | pokerhud/w4p.js (62 KB) | ⚠️ hardcoded key + URL | Live-table DOM scraper + command executor |
| Legacy tournament scrapers | pokerhud/{tournament_scraper*,ws_*,workers/} | ☠️ orphaned | Replaced by mtt; kept only for helper reuse |
| er-remote / er-engine | Docker containers :4000 / :5002 | ☠️ legacy running | Old E&R (Express→Flask→engine, 2 HTTP hops) |
| E-R repo | github.com/abwarren/E-R | ☠️ legacy | Source of old containers + engine branch |
| NEW_E-R repo | github.com/abwarren/NEW_E-R | ☠️ plan-only | Greenfield plan — superseded by this strategy |
| DBs | localhost:5432 | ❌ sprawl | pokerhud (13 MB), er_hands, new_er, sunbet_hands, 5× er_verify_* |

## 2. The Problems (measured)

1. **Three copies of the same backend.** pokerhud/app.py, er-remote container /app/backend/app.py,
   and laptop E&R copies all run independent state (md5s differ). Fixing a bug once doesn't fix it
   everywhere.
2. **Three generations of scrapers.** mtt adapters (canonical) vs orphaned ws_*/tournament_scraper*
   vs w4p.js/extensions. The orphaned set is dead weight that still gets imported by mistake
   (the table_scraper.py import trap).
3. **Hardcoded secrets.** w4p.js ships API key + potlimitomaha.xyz endpoint in source.
4. **5 throwaway DBs** (er_verify_*) + 3 retired DBs (er_hands, new_er, sunbet_hands) when one
   database should serve everything.
5. **Dashboard not running** while its data flows elsewhere — dead UI, no single cockpit.
6. **Two HTTP hops for equity** (browser→Express:4000→Flask:1080→engine:5002) when eval7 is
   already installed locally.
7. **Tenancy is half-done.** mtt tables are site-scoped; the remote-control side and extension
   are PokerBet-only with no tenant key.

## 3. Target Architecture (one app)

```
ONE APP = pokerhud (single repo, single Flask process)
  ├── mtt schema (PG, untouched)      → tournaments/snapshots/players/hands  [tenant: site]
  ├── remote schema (PG, new)         → table state, command queue, sessions  [tenant: site]
  ├── API: dashboard + remote control (one app, blueprints)
  ├── static UI: dashboard + remote grid (SSE push, no polling)
  ├── equity: eval7 imported in-process (no HTTP hop, no engine container)
  └── ONE MV3 extension (HUD + control) with per-site selector profiles
        ├── evenbet.json   (SunBet — sb-play.pkrsrv.com)
        └── betconstruct.json (PokerBet / GoldRush — poker-web.*.co.za)
  └── tenants = sites: site column on every table, selector profile per host,
      adapter registry, dashboard site filter
```

**Tenant rule (separation of topics):** every row carries `site`; every query filters by it;
profiles/adapters are keyed by hostname; site A's data never mixes with site B's in any view.

## 4. Harmonization Principles (rules of the road)

1. **Reuse > rebuild.** If it exists and works (mtt pipeline, adapters, eval7), it stays.
2. **Retire > rewrite.** If it's superseded, delete/archive it — don't keep a second copy.
3. **One source of truth per concern.** Data: PG. Config: env + ~/.pokerhud_pgpass. API config:
   one shared frontend config. Never hardcode keys/URLs in source.
4. **One app, one DB, one process.** New features land in pokerhud; no new repos, no new ports.
5. **Tenants are data, not code.** Adding a site = adding an adapter + selector profile + a
   `sites` row. Zero structural changes.
6. **Tested increments.** Every phase ends with tests green + a demonstrable artifact, tagged.

## 5. Phased Roadmap (each phase reuses, never rebuilds)

### Phase 0 — Freeze & map (this doc)
- [ ] Archive NEW_E-R repo (mark superseded; keep plan history).
- [ ] Add this strategy to pokerhud/docs/; commit + push.
- [ ] Inventory cron jobs touching poker data (mtt 30m, 22:15 daily; extension; dashboard).

### Phase 1 — Database consolidation
- [ ] Drop the 5 `er_verify_*` throwaway DBs.
- [ ] Decide er_hands → `remote` schema migration (only if remote state is still wanted in PG;
      otherwise retire). mtt tables untouched.
- [ ] Retire `new_er` and `sunbet_hands` DBs (plan superseded; sunbet monitor superseded by mtt).
- [ ] Evidence: one poker DB (pokerhud) with mtt + remote schemas; `pg_database` clean.

### Phase 2 — Scraper unification
- [ ] Delete orphaned legacy scrapers (tournament_scraper.py, tournament_scraper_live.py,
      ws_connect.py, ws_discovery.py, workers/) — keep only the reusable helpers already copied
      into mtt adapters. Fix the table_scraper.py import trap in app.py.
- [ ] w4p.js → config-driven (env/extension-settings for API base + key; kill hardcoded
      potlimitomaha.xyz + trk_*).
- [ ] Extension: multi-site selector profiles (evenbet.json + betconstruct.json), hostname-based
      profile switch, site tagged on every snapshot.
- [ ] Evidence: `grep -r "potlimitomaha\|trk_prod"` → zero; extension loads on both hosts.

### Phase 3 — Backend merge
- [ ] Merge dashboard.py + app.py into one Flask app (blueprints), one port (8899), one process.
- [ ] Equity in-process: import eval7 in the merged app; retire er-engine container + /api/engine
      HTTP hop.
- [ ] Retire er-remote container (Express layer dies with it — Flask serves static + API directly).
- [ ] Evidence: one process serves dashboard + remote control; equity roundtrip <100 ms local.

### Phase 4 — Tenant hardening
- [ ] Remote-control state tables get `site` + `(site, table_id, bot_id)` partition (fixes the
      legacy `_tables`-by-table_id collision).
- [ ] Dashboard site filter (All / PokerBet / SunBet) on schedule + players.
- [ ] Selector registry validates profiles at startup (fail fast on site DOM change).
- [ ] Evidence: multi-bot-per-table state test with two sites, no cross-site bleed.

### Phase 5 — Decommission legacy
- [ ] E-R repo archived (read-only); er-remote/er-engine containers stopped; ports 4000/5002 freed.
- [ ] Laptop tunnel config updated to point at pokerhud app port only.
- [ ] Evidence: `docker ps` shows no er-*; ss shows app port only.

### Phase 6 — Efficiency
- [ ] SSE push on table state (replaces polling; legacy unified-frontend analysis already exists
      in E-R docs — reuse it).
- [ ] One extension build (HUD + control merged), one dashboard page (remote grid + equity panel).
- [ ] Evidence: request rate per UI drops ≥90%; dashboard + remote on one page.

## 6. What Gets Retired (summary)

| Item | Action | When |
|------|--------|------|
| er_verify_* DBs (×5) | drop | Phase 1 |
| new_er DB | drop | Phase 1 |
| sunbet_hands DB | drop | Phase 1 |
| er_hands DB | migrate-or-retire | Phase 1 |
| Legacy scrapers (ws_*, tournament_scraper*, workers/) | delete | Phase 2 |
| Hardcoded w4p.js key/URL | env-driven | Phase 2 |
| er-engine container (:5002) | stop/remove | Phase 3 |
| er-remote container (:4000, Express) | stop/remove | Phase 3 |
| E-R repo | archive | Phase 5 |
| NEW_E-R repo | archive | Phase 0 |

## 7. Success Metrics (how we know it's simpler)

| Metric | Before | After |
|--------|--------|-------|
| Repos in cluster | 3 (E-R, pokerhud, NEW_E-R) | 1 (pokerhud) |
| Databases | 9 (4 live + 5 junk) | 1 (pokerhud) |
| App processes | 4+ (dashboard?, app.py, er-remote, er-engine) | 1 |
| Ports | 4000, 5002, 1080, 8899 | 8899 (+5432 PG) |
| Scraper generations | 3 | 1 per concern (mtt adapters + one extension) |
| HTTP hops per snapshot/equity | 2 | 0 |
| Hardcoded secrets in source | ≥2 | 0 |
| Tests | 85 (mtt) | 85 + new (remote, extension, tenant) — all green |

## 8. Decision Log

- 2026-08-12: Greenfield NEW_E-R **rejected** — user: "don't rebuild things that already exist";
  "one application, different tenants"; target = extend pokerhud.
- 2026-08-12: Tenants = poker sites (PokerBet, SunBet/GoldRush), not products, not clients.
- 2026-08-12: Equity stays eval7, moved in-process — never a new engine service.
- 2026-08-12: mtt pipeline is the canonical spine; everything else attaches to it.
