"""PostgreSQL access for the mtt pipeline (schema `mtt` by default).

Idempotency contract:
- tournaments: UNIQUE (site, site_tournament_id) — upsert, never duplicate
- snapshots:   UNIQUE (tournament_id, captured_at) — upsert
- players:     UNIQUE (site, normalized_name) — upsert, identity not merged
- player_tournaments: UNIQUE (player_id, tournament_id)
- raw_events:  UNIQUE (site, capture_id) — deterministic capture ids
- daily_statistics: UNIQUE (stat_date, site, cohort)

Schema name is configurable (MTT_SCHEMA env) so tests run against
mtt_test without touching production tables.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

DEFAULT_DSN = dict(host="localhost", port=5432, dbname="pokerhud",
                   user="warren", password="Gemm@143")


def schema_name() -> str:
    return os.environ.get("MTT_SCHEMA", "mtt")


def dsn() -> dict:
    d = dict(DEFAULT_DSN)
    for k in ("host", "port", "dbname", "user", "password"):
        v = os.environ.get(f"MTT_{k.upper()}")
        if v:
            d[k] = v
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
