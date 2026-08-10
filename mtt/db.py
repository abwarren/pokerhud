"""PostgreSQL access for the mtt pipeline (schema `mtt` by default).

Idempotency contract:
- tournaments: UNIQUE (site, site_tournament_id) — upsert, never duplicate
- snapshots:   UNIQUE (tournament_id, captured_at) — upsert
- players:     UNIQUE (site, normalized_name) — upsert, identity not merged
- player_tournaments: UNIQUE (player_id, tournament_id)
- raw_events:  UNIQUE (site, capture_id) — deterministic capture ids
- daily_statistics: UNIQUE (stat_date, site, cohort)
- hands:       UNIQUE (site, site_hand_id) — deterministic hand ids
- hand_actions: UNIQUE (hand_id, action_order)

Schema name is configurable (MTT_SCHEMA env) so tests run against
mtt_test without touching production tables.

Credentials: read from env (MTT_HOST/MTT_PORT/MTT_DBNAME/MTT_USER/MTT_PASSWORD)
with a local fallback file ~/.pokerhud_pgpass (first line = password).
No credentials are hardcoded in this file.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras


def _local_pgpass() -> Optional[str]:
    """Password from ~/.pokerhud_pgpass (untracked, outside the repo)."""
    try:
        p = Path.home() / ".pokerhud_pgpass"
        if p.exists():
            line = p.read_text().strip().splitlines()
            return line[0] if line else None
    except OSError:
        return None
    return None


def schema_name() -> str:
    return os.environ.get("MTT_SCHEMA", "mtt")


def dsn() -> dict:
    d = dict(host=os.environ.get("MTT_HOST", "localhost"),
             port=int(os.environ.get("MTT_PORT", "5432")),
             dbname=os.environ.get("MTT_DBNAME", "pokerhud"),
             user=os.environ.get("MTT_USER", "warren"))
    password = os.environ.get("MTT_PASSWORD") or _local_pgpass()
    if password:
        d["password"] = password
    return d


def connect():
    return psycopg2.connect(**dsn())


DDL = """
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.sites (
    site_id        TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    platform       TEXT NOT NULL DEFAULT 'unknown'
);

CREATE TABLE IF NOT EXISTS {schema}.tournaments (
    id                SERIAL PRIMARY KEY,
    site              TEXT NOT NULL,
    site_tournament_id TEXT NOT NULL,
    name              TEXT,
    game_type         TEXT,
    format            TEXT,
    currency          TEXT DEFAULT 'ZAR',
    buyin             INTEGER,
    fee               INTEGER,
    total_entry_cost  INTEGER,
    guarantee         INTEGER,
    start_time        TIMESTAMPTZ,
    status            TEXT,
    field_size        INTEGER,
    unique_players    INTEGER,
    entries           INTEGER,
    reentries         INTEGER,
    prize_pool        INTEGER,
    max_players       INTEGER,
    structure_hash    TEXT,
    buyin_band        TEXT,
    field_band        TEXT,
    cohort            TEXT,
    data_quality_score INTEGER DEFAULT 0,
    quality_flags     TEXT[] DEFAULT '{{}}',
    first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site, site_tournament_id)
);
CREATE INDEX IF NOT EXISTS idx_tourn_site_start ON {schema}.tournaments (site, start_time);
CREATE INDEX IF NOT EXISTS idx_tourn_cohort ON {schema}.tournaments (cohort);

CREATE TABLE IF NOT EXISTS {schema}.tournament_snapshots (
    id               SERIAL PRIMARY KEY,
    tournament_id    INTEGER NOT NULL REFERENCES {schema}.tournaments(id) ON DELETE CASCADE,
    captured_at      TIMESTAMPTZ NOT NULL,
    status           TEXT,
    entries          INTEGER,
    players_remaining INTEGER,
    tables_active    INTEGER,
    prize_pool       INTEGER,
    current_level    INTEGER,
    small_blind      INTEGER,
    big_blind        INTEGER,
    ante             INTEGER,
    average_stack    INTEGER,
    late_registration BOOLEAN,
    raw_payload      JSONB,
    UNIQUE (tournament_id, captured_at)
);

CREATE TABLE IF NOT EXISTS {schema}.players (
    id               SERIAL PRIMARY KEY,
    site             TEXT NOT NULL,
    site_player_id   TEXT,
    display_name     TEXT NOT NULL,
    normalized_name  TEXT NOT NULL,
    first_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site, normalized_name)
);
CREATE INDEX IF NOT EXISTS idx_players_site ON {schema}.players (site);

CREATE TABLE IF NOT EXISTS {schema}.player_aliases (
    id         SERIAL PRIMARY KEY,
    player_id  INTEGER NOT NULL REFERENCES {schema}.players(id) ON DELETE CASCADE,
    alias      TEXT NOT NULL,
    source     TEXT,
    UNIQUE (player_id, alias)
);

CREATE TABLE IF NOT EXISTS {schema}.player_tournaments (
    id               SERIAL PRIMARY KEY,
    player_id        INTEGER NOT NULL REFERENCES {schema}.players(id) ON DELETE CASCADE,
    tournament_id    INTEGER NOT NULL REFERENCES {schema}.tournaments(id) ON DELETE CASCADE,
    entry_number     INTEGER,
    starting_stack   INTEGER,
    finish_position  INTEGER,
    prize            INTEGER,
    bounty           INTEGER,
    rebuy_count      INTEGER,
    addon_count      INTEGER,
    UNIQUE (player_id, tournament_id)
);

CREATE TABLE IF NOT EXISTS {schema}.raw_events (
    id              SERIAL PRIMARY KEY,
    site            TEXT NOT NULL,
    capture_id      TEXT NOT NULL,
    tournament_ref  TEXT,
    endpoint        TEXT,
    captured_at     TIMESTAMPTZ NOT NULL,
    parser_version  TEXT NOT NULL,
    raw_payload     JSONB NOT NULL,
    UNIQUE (site, capture_id)
);

CREATE TABLE IF NOT EXISTS {schema}.ingestion_runs (
    run_id               TEXT PRIMARY KEY,
    site                 TEXT NOT NULL,
    started_at           TIMESTAMPTZ NOT NULL,
    completed_at         TIMESTAMPTZ,
    duration_s           REAL,
    tournaments_discovered INTEGER DEFAULT 0,
    tournaments_captured   INTEGER DEFAULT 0,
    tournaments_failed     INTEGER DEFAULT 0,
    players_captured       INTEGER DEFAULT 0,
    hands_captured         INTEGER DEFAULT 0,
    duplicates             INTEGER DEFAULT 0,
    validation_errors      INTEGER DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS {schema}.parser_errors (
    id               SERIAL PRIMARY KEY,
    run_id           TEXT REFERENCES {schema}.ingestion_runs(run_id) ON DELETE CASCADE,
    site             TEXT NOT NULL,
    tournament_ref   TEXT,
    parser_version   TEXT,
    error_type       TEXT NOT NULL,
    message          TEXT
);

CREATE TABLE IF NOT EXISTS {schema}.daily_statistics (
    stat_date        DATE NOT NULL,
    site             TEXT NOT NULL,
    cohort           TEXT NOT NULL,
    tournaments_expected INTEGER DEFAULT 0,
    tournaments_captured INTEGER DEFAULT 0,
    tournaments_complete INTEGER DEFAULT 0,
    tournaments_partial  INTEGER DEFAULT 0,
    tournaments_missing  INTEGER DEFAULT 0,
    entries_total        INTEGER DEFAULT 0,
    prize_pool_total     BIGINT DEFAULT 0,
    generated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (stat_date, site, cohort)
);

-- Explicit cohort assignment history: one row per stable (cohort, bands)
-- assignment; reclassification creates a new row (history preserved).
CREATE TABLE IF NOT EXISTS {schema}.tournament_cohorts (
    id              SERIAL PRIMARY KEY,
    tournament_id   INTEGER NOT NULL REFERENCES {schema}.tournaments(id) ON DELETE CASCADE,
    cohort          TEXT NOT NULL,
    buyin_band      TEXT,
    field_band      TEXT,
    parser_version  TEXT NOT NULL,
    assigned_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tournament_id, cohort, buyin_band, field_band)
);
CREATE INDEX IF NOT EXISTS idx_cohorts_tourn ON {schema}.tournament_cohorts (tournament_id);

CREATE TABLE IF NOT EXISTS {schema}.tables (
    id              SERIAL PRIMARY KEY,
    tournament_id   INTEGER NOT NULL REFERENCES {schema}.tournaments(id) ON DELETE CASCADE,
    site_table_id   TEXT NOT NULL,
    table_name      TEXT,
    UNIQUE (tournament_id, site_table_id)
);

CREATE TABLE IF NOT EXISTS {schema}.table_snapshots (
    id              SERIAL PRIMARY KEY,
    table_id        INTEGER NOT NULL REFERENCES {schema}.tables(id) ON DELETE CASCADE,
    captured_at     TIMESTAMPTZ NOT NULL,
    players_count   INTEGER,
    seats           INTEGER,
    average_stack   INTEGER,
    small_blind     INTEGER,
    big_blind       INTEGER,
    ante            INTEGER,
    UNIQUE (table_id, captured_at)
);

CREATE TABLE IF NOT EXISTS {schema}.hands (
    id              SERIAL PRIMARY KEY,
    site            TEXT NOT NULL,
    site_hand_id    TEXT NOT NULL,
    tournament_id   INTEGER REFERENCES {schema}.tournaments(id) ON DELETE CASCADE,
    table_id        INTEGER REFERENCES {schema}.tables(id) ON DELETE SET NULL,
    hand_number     INTEGER,
    played_at       TIMESTAMPTZ,
    small_blind     INTEGER,
    big_blind       INTEGER,
    ante            INTEGER,
    button_position INTEGER,
    board           TEXT,
    final_pot       INTEGER,
    UNIQUE (site, site_hand_id)
);
CREATE INDEX IF NOT EXISTS idx_hands_tourn ON {schema}.hands (tournament_id);

CREATE TABLE IF NOT EXISTS {schema}.hand_players (
    id              SERIAL PRIMARY KEY,
    hand_id         INTEGER NOT NULL REFERENCES {schema}.hands(id) ON DELETE CASCADE,
    player_id       INTEGER NOT NULL REFERENCES {schema}.players(id) ON DELETE CASCADE,
    seat            INTEGER,
    position        TEXT,
    starting_stack  INTEGER,
    ending_stack    INTEGER,
    hole_cards      TEXT,
    UNIQUE (hand_id, player_id)
);

CREATE TABLE IF NOT EXISTS {schema}.hand_actions (
    id              SERIAL PRIMARY KEY,
    hand_id         INTEGER NOT NULL REFERENCES {schema}.hands(id) ON DELETE CASCADE,
    player_id       INTEGER REFERENCES {schema}.players(id) ON DELETE SET NULL,
    street          TEXT,
    action_type     TEXT NOT NULL,
    amount          INTEGER,
    pot_after       INTEGER,
    action_order    INTEGER NOT NULL,
    UNIQUE (hand_id, action_order)
);

-- ---------------- analytics views ----------------
-- Every view exposes cohort (and where relevant field_band) so a generic
-- query can never silently mix R1000 with lower-stakes tournaments.

CREATE OR REPLACE VIEW {schema}.v_daily_summary AS
SELECT stat_date, site, cohort,
       tournaments_expected, tournaments_captured,
       tournaments_complete, tournaments_partial, tournaments_missing,
       entries_total, prize_pool_total
FROM {schema}.daily_statistics;

CREATE OR REPLACE VIEW {schema}.v_cohort_summary AS
SELECT site, cohort, field_band,
       COUNT(*) AS tournaments,
       COUNT(*) FILTER (WHERE status = 'completed') AS completed,
       COALESCE(SUM(entries), 0) AS entries,
       COALESCE(SUM(prize_pool), 0) AS prize_pool,
       ROUND(COALESCE(AVG(data_quality_score), 0)) AS avg_quality
FROM {schema}.tournaments
WHERE cohort IS NOT NULL
GROUP BY site, cohort, field_band;

-- Per-player performance, explicitly keyed by (cohort, field_band).
-- R1000 rows are separate rows and must never be merged with others.
CREATE OR REPLACE VIEW {schema}.v_player_performance AS
SELECT p.id AS player_id,
       p.site,
       p.display_name,
       p.normalized_name,
       t.cohort,
       t.field_band,
       t.game_type,
       COUNT(DISTINCT t.id) AS tournaments_played,
       COUNT(DISTINCT pt.tournament_id) FILTER (WHERE COALESCE(pt.prize, 0) > 0) AS cash_count,
       COALESCE(SUM(pt.prize), 0) AS total_prizes,
       COALESCE(SUM(pt.bounty), 0) AS total_bounty,
       MIN(pt.finish_position) AS best_finish,
       COALESCE(SUM(t.total_entry_cost * COALESCE(pt.entry_number, 1)), 0) AS total_cost,
       COALESCE(SUM(pt.prize), 0) - COALESCE(SUM(t.total_entry_cost * COALESCE(pt.entry_number, 1)), 0) AS net_profit,
       ROUND(CASE WHEN COALESCE(SUM(t.total_entry_cost * COALESCE(pt.entry_number, 1)), 0) > 0
                  THEN (COALESCE(SUM(pt.prize), 0) / SUM(t.total_entry_cost * COALESCE(pt.entry_number, 1))) * 100 - 100
                  ELSE 0 END, 1) AS roi_pct
FROM {schema}.players p
JOIN {schema}.player_tournaments pt ON pt.player_id = p.id
JOIN {schema}.tournaments t ON t.id = pt.tournament_id
GROUP BY p.id, p.site, p.display_name, p.normalized_name,
         t.cohort, t.field_band, t.game_type;

-- Per-day lifecycle view: first/last snapshot deltas per tournament.
CREATE OR REPLACE VIEW {schema}.v_tournament_lifecycle AS
SELECT t.id AS tournament_id, t.site, t.cohort, t.name,
       t.start_time, t.status AS current_status,
       s_first.captured_at AS first_captured_at,
       s_first.entries AS first_entries,
       s_first.players_remaining AS first_players_remaining,
       s_last.captured_at AS last_captured_at,
       s_last.entries AS last_entries,
       s_last.players_remaining AS last_players_remaining,
       s_last.prize_pool AS last_prize_pool,
       s_last.small_blind AS last_small_blind,
       s_last.big_blind AS last_big_blind,
       s_last.ante AS last_ante,
       COUNT(s.id) AS snapshot_count
FROM {schema}.tournaments t
LEFT JOIN {schema}.tournament_snapshots s ON s.tournament_id = t.id
LEFT JOIN LATERAL (
    SELECT captured_at, entries, players_remaining FROM {schema}.tournament_snapshots
    WHERE tournament_id = t.id ORDER BY captured_at ASC LIMIT 1
) s_first ON true
LEFT JOIN LATERAL (
    SELECT captured_at, entries, players_remaining, prize_pool,
           small_blind, big_blind, ante FROM {schema}.tournament_snapshots
    WHERE tournament_id = t.id ORDER BY captured_at DESC LIMIT 1
) s_last ON true
GROUP BY t.id, s_first.captured_at, s_first.entries, s_first.players_remaining,
         s_last.captured_at, s_last.entries, s_last.players_remaining,
         s_last.prize_pool, s_last.small_blind, s_last.big_blind, s_last.ante;
"""


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL.format(schema=schema_name()))
        for site, platform in (("pokerbet", "betconstruct-skillgames"),
                               ("sunbet", "evenbet-pokeralpha")):
            cur.execute(
                f"INSERT INTO {schema_name()}.sites (site_id, name, platform) "
                "VALUES (%s, %s, %s) ON CONFLICT (site_id) DO NOTHING",
                (site, site, platform))
    conn.commit()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_run(conn, run_id: str, site: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO {schema_name()}.ingestion_runs (run_id, site, started_at) "
            "VALUES (%s, %s, %s) ON CONFLICT (run_id) DO NOTHING",
            (run_id, site, now_iso()))
    conn.commit()


def complete_run(conn, run_id: str, counters: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {schema_name()}.ingestion_runs SET completed_at=%s, duration_s=%s, "
            "tournaments_discovered=%s, tournaments_captured=%s, tournaments_failed=%s, "
            "players_captured=%s, hands_captured=%s, duplicates=%s, validation_errors=%s, "
            "status=%s WHERE run_id=%s",
            (now_iso(), counters.get("duration_s"), counters.get("discovered", 0),
             counters.get("captured", 0), counters.get("failed", 0),
             counters.get("players", 0), counters.get("hands", 0),
             counters.get("duplicates", 0), counters.get("validation_errors", 0),
             counters.get("status", "completed"), run_id))
    conn.commit()


def upsert_tournament(conn, t: dict, score: int, flags: list) -> str:
    """Insert or update canonical tournament. Returns 'inserted'|'updated'."""
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {schema_name()}.tournaments
                (site, site_tournament_id, name, game_type, format, currency,
                 buyin, fee, total_entry_cost, guarantee, start_time, status,
                 field_size, unique_players, entries, reentries, prize_pool,
                 max_players, structure_hash, buyin_band, field_band, cohort,
                 data_quality_score, quality_flags, first_seen_at, last_seen_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now())
                ON CONFLICT (site, site_tournament_id) DO UPDATE SET
                  name=EXCLUDED.name, game_type=EXCLUDED.game_type,
                  format=EXCLUDED.format, buyin=EXCLUDED.buyin, fee=EXCLUDED.fee,
                  total_entry_cost=EXCLUDED.total_entry_cost,
                  guarantee=EXCLUDED.guarantee, start_time=EXCLUDED.start_time,
                  status=EXCLUDED.status, field_size=EXCLUDED.field_size,
                  unique_players=EXCLUDED.unique_players, entries=EXCLUDED.entries,
                  reentries=EXCLUDED.reentries, prize_pool=EXCLUDED.prize_pool,
                  max_players=EXCLUDED.max_players,
                  structure_hash=EXCLUDED.structure_hash,
                  buyin_band=EXCLUDED.buyin_band, field_band=EXCLUDED.field_band,
                  cohort=EXCLUDED.cohort,
                  data_quality_score=EXCLUDED.data_quality_score,
                  quality_flags=EXCLUDED.quality_flags,
                  last_seen_at=now()""",
            (t["site"], t["site_tournament_id"], t["name"], t["game_type"],
             t["format"], t["currency"], t["buyin"], t["fee"],
             t["total_entry_cost"], t["guarantee"], t["start_time"],
             t["status"], t["field_size"], t["unique_players"], t["entries"],
             t["reentries"], t["prize_pool"], t["max_players"],
             t["structure_hash"], t.get("buyin_band"), t.get("field_band"),
             t.get("cohort"), score, flags))
        return "updated" if cur.rowcount and cur.statusmessage.startswith("UPDATE") else "inserted"


def tournament_id(conn, site: str, site_tournament_id: str) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT id FROM {schema_name()}.tournaments WHERE site=%s AND site_tournament_id=%s",
            (site, site_tournament_id))
        row = cur.fetchone()
        return row[0] if row else None


def upsert_snapshot(conn, tournament_pk: int, snap: dict, raw_payload=None) -> str:
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {schema_name()}.tournament_snapshots
                (tournament_id, captured_at, status, entries, players_remaining,
                 tables_active, prize_pool, current_level, small_blind, big_blind,
                 ante, average_stack, late_registration, raw_payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tournament_id, captured_at) DO UPDATE SET
                  status=EXCLUDED.status, entries=EXCLUDED.entries,
                  players_remaining=EXCLUDED.players_remaining,
                  tables_active=EXCLUDED.tables_active, prize_pool=EXCLUDED.prize_pool,
                  current_level=EXCLUDED.current_level, small_blind=EXCLUDED.small_blind,
                  big_blind=EXCLUDED.big_blind, ante=EXCLUDED.ante,
                  average_stack=EXCLUDED.average_stack,
                  late_registration=EXCLUDED.late_registration,
                  raw_payload=EXCLUDED.raw_payload""",
            (tournament_pk, snap["captured_at"], snap["status"], snap["entries"],
             snap["players_remaining"], snap["tables_active"], snap["prize_pool"],
             snap["current_level"], snap["small_blind"], snap["big_blind"],
             snap["ante"], snap["average_stack"], snap["late_registration"],
             psycopg2.extras.Json(raw_payload) if raw_payload is not None else None))
        return "updated" if cur.rowcount and cur.statusmessage.startswith("UPDATE") else "inserted"


def upsert_player(conn, site: str, display_name: str, site_player_id=None,
                  normalized_name=None) -> int:
    norm = (normalized_name or (display_name or "").strip().lower())
    if not norm:
        return 0
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {schema_name()}.players
                (site, site_player_id, display_name, normalized_name, first_seen, last_seen)
                VALUES (%s,%s,%s,%s,now(),now())
                ON CONFLICT (site, normalized_name) DO UPDATE SET
                  last_seen=now(),
                  site_player_id=COALESCE(EXCLUDED.site_player_id,
                                          {schema_name()}.players.site_player_id)
                RETURNING id""",
            (site, site_player_id, display_name, norm))
        return cur.fetchone()[0]


def upsert_player_tournament(conn, player_id: int, tournament_pk: int, pr: dict) -> str:
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {schema_name()}.player_tournaments
                (player_id, tournament_id, entry_number, starting_stack,
                 finish_position, prize, bounty, rebuy_count, addon_count)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (player_id, tournament_id) DO UPDATE SET
                  entry_number=EXCLUDED.entry_number,
                  starting_stack=EXCLUDED.starting_stack,
                  finish_position=EXCLUDED.finish_position,
                  prize=EXCLUDED.prize, bounty=EXCLUDED.bounty,
                  rebuy_count=EXCLUDED.rebuy_count, addon_count=EXCLUDED.addon_count""",
            (player_id, tournament_pk, pr.get("entry_number"),
             pr.get("starting_stack"), pr.get("finish_position"), pr.get("prize"),
             pr.get("bounty"), pr.get("rebuy_count"), pr.get("addon_count")))
        return "updated" if cur.rowcount and cur.statusmessage.startswith("UPDATE") else "inserted"


def insert_raw_event(conn, site: str, capture_id: str, tournament_ref: str,
                     endpoint: str, captured_at: str, parser_version: str,
                     payload: dict) -> str:
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {schema_name()}.raw_events
                (site, capture_id, tournament_ref, endpoint, captured_at,
                 parser_version, raw_payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (site, capture_id) DO NOTHING
                RETURNING id""",
            (site, capture_id, tournament_ref, endpoint, captured_at,
             parser_version, psycopg2.extras.Json(payload)))
        return "inserted" if cur.fetchone() else "duplicate"


def log_parser_error(conn, run_id: str, site: str, tournament_ref: str,
                     error_type: str, message: str, parser_version: str = "1.0.0") -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO {schema_name()}.parser_errors "
            "(run_id, site, tournament_ref, parser_version, error_type, message) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (run_id, site, tournament_ref, parser_version, error_type, message))
    conn.commit()


def query(conn, sql: str, params: tuple = ()):
    """Execute SQL; return rows for row-returning statements, [] otherwise."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        if cur.description is None:  # UPDATE/DELETE/DDL — no result set
            return []
        return cur.fetchall()


def upsert_daily_stat(conn, stat_date, site, cohort, counts: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {schema_name()}.daily_statistics
                (stat_date, site, cohort, tournaments_expected, tournaments_captured,
                 tournaments_complete, tournaments_partial, tournaments_missing,
                 entries_total, prize_pool_total, generated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                ON CONFLICT (stat_date, site, cohort) DO UPDATE SET
                  tournaments_expected=EXCLUDED.tournaments_expected,
                  tournaments_captured=EXCLUDED.tournaments_captured,
                  tournaments_complete=EXCLUDED.tournaments_complete,
                  tournaments_partial=EXCLUDED.tournaments_partial,
                  tournaments_missing=EXCLUDED.tournaments_missing,
                  entries_total=EXCLUDED.entries_total,
                  prize_pool_total=EXCLUDED.prize_pool_total,
                  generated_at=now()""",
            (stat_date, site, cohort, counts.get("expected", 0),
             counts.get("captured", 0), counts.get("complete", 0),
             counts.get("partial", 0), counts.get("missing", 0),
             counts.get("entries_total", 0), counts.get("prize_pool_total", 0)))
    conn.commit()


def upsert_cohort(conn, tournament_pk: int, cohort, buyin_band, field_band,
                  parser_version: str) -> None:
    """Record an explicit cohort assignment (history preserved on change)."""
    if cohort is None:
        return
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {schema_name()}.tournament_cohorts
                (tournament_id, cohort, buyin_band, field_band, parser_version, assigned_at)
                VALUES (%s,%s,%s,%s,%s,now())
                ON CONFLICT (tournament_id, cohort, buyin_band, field_band) DO UPDATE SET
                  assigned_at=now()""",
            (tournament_pk, cohort, buyin_band, field_band, parser_version))
    conn.commit()


def update_quality(conn, tournament_pk: int, score: int, flags: list) -> None:
    """Re-score a tournament after lifecycle data arrives (e.g. no results)."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {schema_name()}.tournaments SET data_quality_score=%s, "
            f"quality_flags=%s WHERE id=%s",
            (score, flags, tournament_pk))
    conn.commit()


def upsert_table(conn, tournament_pk: int, site_table_id: str,
                 table_name=None) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {schema_name()}.tables
                (tournament_id, site_table_id, table_name)
                VALUES (%s,%s,%s)
                ON CONFLICT (tournament_id, site_table_id) DO UPDATE SET
                  table_name=COALESCE(EXCLUDED.table_name, {schema_name()}.tables.table_name)
                RETURNING id""",
            (tournament_pk, site_table_id, table_name))
        return cur.fetchone()[0]


def upsert_table_snapshot(conn, table_pk: int, snap: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {schema_name()}.table_snapshots
                (table_id, captured_at, players_count, seats, average_stack,
                 small_blind, big_blind, ante)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (table_id, captured_at) DO UPDATE SET
                  players_count=EXCLUDED.players_count, seats=EXCLUDED.seats,
                  average_stack=EXCLUDED.average_stack,
                  small_blind=EXCLUDED.small_blind, big_blind=EXCLUDED.big_blind,
                  ante=EXCLUDED.ante""",
            (table_pk, snap.get("captured_at"), snap.get("players_count"),
             snap.get("seats"), snap.get("average_stack"), snap.get("small_blind"),
             snap.get("big_blind"), snap.get("ante")))
    conn.commit()


def upsert_hand(conn, site: str, h: dict, tournament_pk=None, table_pk=None) -> Optional[int]:
    """Insert a canonical hand. Returns hand pk or None if no site_hand_id."""
    if not h.get("site_hand_id"):
        return None
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {schema_name()}.hands
                (site, site_hand_id, tournament_id, table_id, hand_number,
                 played_at, small_blind, big_blind, ante, button_position,
                 board, final_pot)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (site, site_hand_id) DO UPDATE SET
                  tournament_id=COALESCE(EXCLUDED.tournament_id, {schema_name()}.hands.tournament_id),
                  table_id=COALESCE(EXCLUDED.table_id, {schema_name()}.hands.table_id),
                  played_at=COALESCE(EXCLUDED.played_at, {schema_name()}.hands.played_at),
                  board=COALESCE(EXCLUDED.board, {schema_name()}.hands.board),
                  final_pot=COALESCE(EXCLUDED.final_pot, {schema_name()}.hands.final_pot)
                RETURNING id""",
            (site, h["site_hand_id"], tournament_pk, table_pk,
             h.get("hand_number"), h.get("played_at"), h.get("small_blind"),
             h.get("big_blind"), h.get("ante"), h.get("button_position"),
             h.get("board"), h.get("final_pot")))
        return cur.fetchone()[0]


def upsert_hand_player(conn, hand_pk: int, player_pk: int, hp: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {schema_name()}.hand_players
                (hand_id, player_id, seat, position, starting_stack, ending_stack, hole_cards)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (hand_id, player_id) DO UPDATE SET
                  seat=EXCLUDED.seat, position=EXCLUDED.position,
                  starting_stack=EXCLUDED.starting_stack,
                  ending_stack=EXCLUDED.ending_stack,
                  hole_cards=COALESCE(EXCLUDED.hole_cards, {schema_name()}.hand_players.hole_cards)""",
            (hand_pk, player_pk, hp.get("seat"), hp.get("position"),
             hp.get("starting_stack"), hp.get("ending_stack"), hp.get("hole_cards")))
    conn.commit()


def upsert_hand_action(conn, hand_pk: int, player_pk, a: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {schema_name()}.hand_actions
                (hand_id, player_id, street, action_type, amount, pot_after, action_order)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (hand_id, action_order) DO UPDATE SET
                  player_id=EXCLUDED.player_id, street=EXCLUDED.street,
                  action_type=EXCLUDED.action_type, amount=EXCLUDED.amount,
                  pot_after=EXCLUDED.pot_after""",
            (hand_pk, player_pk, a.get("street"), a.get("action_type"),
             a.get("amount"), a.get("pot_after"), a.get("action_order")))
    conn.commit()
