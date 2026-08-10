# PokerHUD — Multi-Tier Tournament Pipeline (MTT)

Status: IMPLEMENTED (2026-08-11) — see docs/security-audit.md and the
        ops section below. Plan was approved before code (committed 97aca33).
Date: 2026-08-10
Repo: github.com/abwarren/pokerhud

## 1. Objective

Turn pokerhud into a reliable daily tournament data capture platform for
**SunBet** and **PokerBet**:

- Capture ALL tournaments (every buy-in level, not just 10K+ GTD) every day
- Normalize both sites into one canonical schema
- Preserve raw source payloads forever (reparseable)
- Classify every tournament into bands + cohorts
- **R1,000 buy-in tournaments are their own cohort — never mixed with
  smaller-stake games in analytics**
- Track tournament lifecycle via repeated snapshots (entries, blinds, prize pool)
- Daily reconciliation: expected vs captured vs complete vs missing
- Idempotent ingestion (double-run = no duplicates)
- Dashboard/report shows accurate per-cohort numbers

## 2. Current state (audit, 2026-08-10)

| Component | State |
|---|---|
| `tournament_scraper.py` | PokerBet WS+REST scraper; stale session tokens; CMS REST works without auth; 10K+ filter only |
| `table_scraper.py` | Per-table hand scraper; tiered storage `scraped_data/1k` + `high_rollers` |
| `workers/` | 5-worker pipeline, NOT wired to cron, unused |
| `dashboard.py` | Flask :8899, reads public schema tables |
| Postgres `pokerhud` | 6 old tables, ALL EMPTY (0 rows) |
| Cron | 4 poker jobs erroring (no model configured) |
| `extension/` | Chrome MV3 HUD, untracked |

Problems: no SunBet tournament ingestion at all, no results capture, no
canonical schema, no raw preservation, no classification, no data quality,
no reconciliation, empty DB, broken cron.

## 3. Target architecture

```
SUNBET ──┐                      POKERBET ──┐
(EvenBet)│                              (BetConstruct)│
         ▼                                      ▼
   adapters/sunbet.py                  adapters/pokerbet.py
   (canonical interface)               (canonical interface)
         │                                      │
         └──────────────┬───────────────────────┘
                        ▼
                 Raw Store (raw_events)
                        ▼
                 Normalizer + Classifier
                  (bands, R1000 cohort)
                        ▼
              PostgreSQL schema `mtt`
     (tournaments, snapshots, players, results,
      raw_events, ingestion_runs, quality)
                        ▼
            Daily Ledger + Report (CLI + API)
                        ▼
               Analytics (cohort-separated)
```

Golden rules:
1. Site identity first: `(site, site_tournament_id)` is canonical — never name.
2. Raw before parse: every capture stores the original payload + parser version.
3. R1000 cohort: `cohort='R1000'` for tournaments with a R1,000 GUARANTEE
   (the R1k GTD tier — "R1000" means the guarantee, not the buy-in). All
   stats filters must include cohort; analytics never mix R1000 with
   MICRO/SMALL/MID/HIGH.
4. Idempotent: unique constraints + upserts; reruns do not duplicate.
5. Accuracy over completeness: missing data is FLAGGED, never silently filled.

## 4. Canonical schema (Postgres, schema `mtt`)

Old public tables stay untouched (dashboard + extension depend on them).

- `sites` — site_id, name, platform
- `tournaments` — canonical identity (site, site_tournament_id UNIQUE),
  name, game_type, format, currency, buyin, fee, total_entry_cost,
  guarantee, start_time, status, field_size, unique_players, entries,
  reentries, prize_pool, max_players, structure_hash, buyin_band,
  field_band, cohort, first_seen_at, last_seen_at, data_quality_score
- `tournament_snapshots` — captured_at, status, entries, players_remaining,
  tables_active, prize_pool, current_level, small_blind, big_blind, ante,
  average_stack, late_registration, raw_payload
- `players` — site, site_player_id, display_name, normalized_name,
  first_seen, last_seen
- `player_aliases` — player_id, alias, source
- `player_tournaments` — player_id, tournament_id, finish_position, prize,
  entry_number, starting_stack, rebuy_count, addon_count (UNIQUE player+tournament)
- `raw_events` — site, capture_id (UNIQUE), tournament_ref, captured_at,
  endpoint, parser_version, raw_payload jsonb
- `ingestion_runs` — run_id, site, started_at, completed_at, duration_s,
  counters (discovered/captured/failed/players/dupes/errors), status
- `parser_errors` — run_id, site, tournament_ref, parser_version, error_type, message
- `daily_statistics` — stat_date, site, cohort, expected, captured,
  complete, partial, missing, entries, prize_pool_total (UNIQUE date+site+cohort)

Band definitions (classifier):

```
buyin (ZAR)      buyin_band
< 100            MICRO
100 – 499        SMALL
500 – 999        MID
>= 1000          HIGH

entries          field_band
1 – 50           TINY_FIELD
51 – 150         SMALL_FIELD
151 – 500        MEDIUM_FIELD
501 – 999        LARGE_FIELD
>= 1000          1000_PLUS_FIELD
```

`cohort` rule (user correction 2026-08-11): **"R1000" = the R1,000
GUARANTEE tier** (a tournament whose guarantee is exactly R1,000), NOT the
buy-in. Those tournaments get `cohort = 'R1000'` and are never mixed with
other tiers in analytics. Every other tournament carries its buyin_band as
cohort.

## 5. Implementation

New package `mtt/` (repo root) + `tests/`:

```
mtt/
  __init__.py
  config.py          # env-driven: DB DSN, raw dir, parser version
  db.py              # connection, upsert helpers (idempotent)
  classifier.py      # buyin_band / field_band / cohort
  normalize.py       # adapter dict -> canonical row + raw payload
  quality.py         # flags + data_quality_score
  rawstore.py        # raw_events write + filesystem mirror (raw/<site>/...)
  ledger.py          # daily reconciliation -> daily_statistics + report text
  adapters/
    __init__.py      # SiteAdapter protocol
    pokerbet.py      # BetConstruct: CMS REST (no auth) + WS live (token)
    sunbet.py        # EvenBet PokerAlpha: lobby REST/DOM
  run.py             # CLI: ingest --site, daily --date, report, export
tests/
  fixtures/          # versioned sample payloads (real captures)
  test_classifier.py
  test_normalize.py
  test_quality.py
  test_adapters.py   # fixture-driven
  test_pipeline.py   # integration: adapter -> raw -> db
  test_e2e.py        # full pipeline, idempotency, reparse
```

Adapters expose the canonical interface:

```python
class SiteAdapter:
    site: str
    def discover(self) -> list[dict]       # schedule: canonical tournament dicts
    def snapshot(self, ref) -> dict | None # lifecycle snapshot
    def results(self, ref) -> dict | None  # winners/payouts if available
    def hand_data(self, ref) -> list[dict] # where available (later phase)
```

Each adapter returns (canonical_dict, raw_payload); the pipeline stores raw
first, then normalizes, then writes.

## 6. Daily operation

- `mtt run.py ingest --site pokerbet` and `--site sunbet` — every 30 min
  during SA poker hours (14:00–23:59), discovery + snapshots of running events
- `mtt run.py daily --date <d>` — end-of-day reconciliation + ledger
- Cron: no_agent script jobs pinned with model (existing 4 jobs are broken:
  no model configured — fix at wiring time)
- Output: daily report = expected/captured/complete/partial/missing per
  site + cohort; R1000 section isolated

## 7. Operations (implemented)

```bash
python3 -m mtt.run init-db                        # create schema mtt
python3 -m mtt.run ingest --site pokerbet         # CMS + (WS when tokens set)
MTT_SB_INPUT=/path python3 -m mtt.run ingest --site sunbet   # file payloads
python3 -m mtt.run ingest --site sunbet --browser  # Selenium lobby collector
python3 -m mtt.run daily --date 2026-08-11         # reconcile -> daily_statistics
python3 -m mtt.run report --date 2026-08-11        # print daily ledger
python3 -m mtt.run stats [--site X] [--cohort R1000]
python3 -m mtt.run analytics [--site X] [--cohort R1000] [--min-tournaments N]
python3 -m mtt.run export --date <d> [--site X] [--out file.json]
python3 -m mtt.run runs                            # observability: last runs
```

Env: `MTT_SCHEMA` (default mtt), `MTT_HOST/PORT/DBNAME/USER/PASSWORD`,
`MTT_RAW_DIR` (default raw), `MTT_PB_TOKEN/MTT_PB_CLIENT_ID/MTT_PB_PLAYER_ID`
(WS live — optional, CMS-only otherwise), `MTT_SB_INPUT` (SunBet file mode).

SunBet live capture needs a browser session with SunBet cookies
(`--browser`, Selenium) or EvenBet-shaped JSON payloads dropped in
`MTT_SB_INPUT` (files are moved to `processed/` after ingestion).
See the poker-tooling skill: evenbet-cookie-injection.md.

Known source limitations: results/payouts are not exposed by either site's
public endpoints; PokerBet hand history API is Cloudflare-gated (needs
session headers); SunBet hands need a live table session. All are captured
as documented gaps (parser_errors / NO_RESULTS quality flag), never faked.

## 8. Testing

- Unit: classifier (band edges, R1000 guarantee tier), normalizer, quality scoring
- Integration: fixture payload -> adapter -> raw -> DB -> classification
- E2E: full pipeline against fixtures, run 3x fresh, plus double-run
  idempotency check, plus reparse (parser v2 on same raw)
- Live smoke: PokerBet CMS endpoint (auth-free) where reachable

## 9. Acceptance

- All tournaments of both sites ingested daily (live where endpoints allow,
  else documented as source limitation)
- R1000 cohort isolated in DB + report
- Raw preserved, idempotent, quality-scored, reconciled
- Tests green; E2E looped 3x; known limitations documented
