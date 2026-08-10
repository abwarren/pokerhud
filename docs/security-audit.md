# Security Audit — PokerHUD

Date: 2026-08-11
Scope: tracked source files in github.com/abwarren/pokerhud
Result: all hardcoded credentials removed from the working tree.
**Git history still contains the old values — ROTATE them.**

## Findings (before remediation)

| File | Credential | Risk |
|---|---|---|
| `mtt/db.py` | Postgres password `Gemm@143` | DB full access |
| `dashboard.py` | Postgres password `Gemm@143` | DB full access |
| `tournament_scraper.py` | `TOKEN` `2F90D0…` (BetConstruct WS session) | player session hijack |
| `tournament_scraper.py` | `CLIENT_ID`, `CLIENT_ID_HASH`, `PLAYER_ID` | account impersonation |
| `table_scraper.py` | same WS token/client/player IDs | account impersonation |
| `ws_connect.py` | same | account impersonation |
| `ws_discovery.py` | same | account impersonation |
| `tournament_scraper_live.py` | Supabase anon key (JWT) | anon API access (RLS-scoped) |
| `workers/worker5_timeseries_ledger.py` | Supabase **service-role** key (JWT) | **full Supabase admin** — worst finding |
| `workers/worker1..4` | Postgres password `pokerhud` (user `warrenabrahams`) | DB access |

The two Supabase keys were already truncated placeholders in some files but
the full JWTs had been committed at some point (`git log` history). The
service-role key grants unrestricted access to the Supabase project — treat
as compromised.

## Remediation applied

- `mtt/db.py`, `dashboard.py`, `workers/worker1..4`: credentials read from
  `MTT_*` env vars, falling back to `~/.pokerhud_pgpass` (untracked, outside
  the repo, first line = password).
- `mtt/adapters/pokerbet.py`: `MTT_PB_TOKEN`, `MTT_PB_CLIENT_ID`,
  `MTT_PB_PLAYER_ID` env-only; no defaults. Degrades to CMS-only when unset
  and records `ws_stale` so the gap is visible.
- Legacy scrapers (`tournament_scraper.py`, `table_scraper.py`,
  `ws_connect.py`, `ws_discovery.py`, `tournament_scraper_live.py`,
  `workers/worker5`): `PB_*` / `SUPABASE_*` env-only.
- `tests/test_security.py` guards the working tree against reintroduction.

## REQUIRED ACTIONS (user)

1. **Rotate the Supabase service-role key** (Supabase dashboard → Settings →
   API → Service Role) — it is in git history.
2. **Rotate the Supabase anon key** if the project's RLS does not fully
   restrict anonymous access.
3. **Change the Postgres password** for `warren` and update
   `~/.pokerhud_pgpass` (and any CI secret).
4. **BetConstruct WS tokens** are session-specific and expire on their own;
   refresh via a browser network trace and export as `MTT_PB_TOKEN` /
   `MTT_PB_CLIENT_ID` / `MTT_PB_PLAYER_ID` when needed.
5. Consider `git filter-repo` to scrub history if the repo ever becomes
   public. The Supabase project id `kzqrdtagpykoylhuqcyv` is also exposed.

## What NOT to do

- Do not add `.env` to the repo; do not paste secrets into issues/commits.
- Do not disable `test_security.py` to "pass" — it is the tripwire.
