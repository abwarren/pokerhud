"""Cohort-separated analytics over the canonical mtt schema.

Every query returns rows that carry cohort (and where relevant field_band)
so callers can never accidentally merge R1000 with lower-stakes tournaments.
R1000 rows are always their own rows; filters are explicit parameters, never
silent joins.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from . import db, ledger


def _where(site=None, cohort=None, field_band=None) -> tuple:
    clauses, params = [], []
    if site:
        clauses.append("site = %s")
        params.append(site)
    if cohort:
        clauses.append("cohort = %s")
        params.append(cohort)
    if field_band:
        clauses.append("field_band = %s")
        params.append(field_band)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", tuple(params)


def player_performance(conn, site: Optional[str] = None,
                       cohort: Optional[str] = None,
                       field_band: Optional[str] = None,
                       min_tournaments: int = 1,
                       limit: int = 50) -> list:
    """Per-player performance keyed by (site, cohort, field_band).

    Sorting: roi_pct desc, then tournaments_played desc. R1000 players are
    separate rows from lower-stake players — never mixed.
    """
    w, params = _where(site, cohort, field_band)
    min_clause = (" AND " if w else " WHERE ") + "tournaments_played >= %s"
    rows = db.query(
        conn,
        f"""SELECT player_id, site, display_name, normalized_name,
                   cohort, field_band, game_type,
                   tournaments_played, cash_count, total_prizes, total_bounty,
                   best_finish, total_cost, net_profit, roi_pct
            FROM {db.schema_name()}.v_player_performance {w}{min_clause}
            ORDER BY roi_pct DESC, tournaments_played DESC
            LIMIT %s""",
        params + (min_tournaments, limit))
    return rows


def cohort_summary(conn, site: Optional[str] = None) -> list:
    """Per (site, cohort, field_band) tournament summary."""
    w, params = _where(site)
    return db.query(
        conn,
        f"""SELECT site, cohort, field_band, tournaments, completed,
                   entries, prize_pool, avg_quality
            FROM {db.schema_name()}.v_cohort_summary {w}
            ORDER BY site, cohort, field_band""",
        params)


def daily_summary(conn, day: date, site: Optional[str] = None) -> list:
    """Persisted daily_statistics rows for a day, cohort-separated."""
    w = " WHERE stat_date = %s" + (" AND site = %s" if site else "")
    params: tuple = (day, site) if site else (day,)
    return db.query(
        conn,
        f"""SELECT stat_date, site, cohort, tournaments_expected,
                   tournaments_captured, tournaments_complete,
                   tournaments_partial, tournaments_missing,
                   entries_total, prize_pool_total
            FROM {db.schema_name()}.v_daily_summary {w}
            ORDER BY site, cohort""",
        params)


def export_day(conn, day: date, site: Optional[str] = None) -> dict:
    """Full day export: daily summary + cohort summary + player performance."""
    start, end = ledger.sa_day_bounds(day)
    return {
        "date": day.isoformat(),
        "site": site,
        "daily": daily_summary(conn, day, site),
        "cohorts": cohort_summary(conn, site),
        "players": player_performance(conn, site, limit=1000),
        "r1000": {
            "tournaments": db.query(
                conn,
                f"""SELECT site, cohort, name, buyin, fee, total_entry_cost,
                           guarantee, start_time, status, field_size, entries,
                           prize_pool, data_quality_score
                    FROM {db.schema_name()}.tournaments
                    WHERE cohort = 'R1000'
                      AND start_time >= %s AND start_time < %s
                      {("AND site = %s" if site else "")}
                    ORDER BY site, start_time""",
                tuple([start, end] + ([site] if site else []))),
        },
    }
