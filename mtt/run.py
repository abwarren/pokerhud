#!/usr/bin/env python3
"""mtt CLI — daily tournament pipeline for SunBet + PokerBet.

Commands:
  ingest   --site {pokerbet,sunbet}   run one capture tick (discover+snapshots+results)
  init-db                            create schema + tables
  daily    --date YYYY-MM-DD [--site] reconcile day -> daily_statistics
  report   --date YYYY-MM-DD [--site] print the daily ledger report
  stats    [--site] [--cohort R1000]  quick DB stats (cohort-separated)

Env: MTT_SCHEMA (default mtt), MTT_HOST/PORT/DBNAME/USER/PASSWORD,
     MTT_RAW_DIR (default raw).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta

from . import db, ledger
from .adapters import get_adapter
from .pipeline import ingest


def cmd_init_db(_a):
    conn = db.connect()
    db.ensure_schema(conn)
    print(f"schema {db.schema_name()} ready")
    conn.close()


def cmd_ingest(a):
    conn = db.connect()
    db.ensure_schema(conn)
    adapter = get_adapter(a.site)
    counters = ingest(conn, adapter, raw_dir=a.raw_dir)
    print(json.dumps(counters, indent=2))
    conn.close()
    if counters["status"] != "completed":
        sys.exit(2)


def cmd_daily(a):
    conn = db.connect()
    db.ensure_schema(conn)
    day = date.fromisoformat(a.date)
    report = ledger.reconcile(conn, day, a.site)
    print(f"reconciled {day.isoformat()}: {len(report)} site/cohort rows")
    conn.close()


def cmd_report(a):
    conn = db.connect()
    db.ensure_schema(conn)
    day = date.fromisoformat(a.date)
    report = ledger.reconcile(conn, day, a.site)
    print(ledger.render_report(report, day))
    conn.close()


def cmd_stats(a):
    conn = db.connect()
    db.ensure_schema(conn)
    s = db.schema_name()
    where, params = [], []
    if a.site:
        where.append("site=%s")
        params.append(a.site)
    if a.cohort:
        where.append("cohort=%s")
        params.append(a.cohort)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.query(
        conn,
        f"""SELECT site, cohort, COUNT(*) AS tournaments,
                   COUNT(*) FILTER (WHERE status='completed') AS completed,
                   COALESCE(SUM(entries),0) AS entries,
                   COALESCE(SUM(prize_pool),0) AS prize_pool,
                   ROUND(AVG(data_quality_score)) AS avg_score
            FROM {s}.tournaments {w}
            GROUP BY site, cohort ORDER BY site, cohort""",
        tuple(params))
    for r in rows:
        print(f"{r['site']:<10} {r['cohort']:<12} n={r['tournaments']:<4} "
              f"completed={r['completed']:<4} entries={r['entries']:<8} "
              f"prize=R{r['prize_pool']:,} avg_score={r['avg_score']}")
    conn.close()


def cmd_analytics(a):
    """Cohort-separated player performance (R1000 isolated by design)."""
    from . import analytics
    conn = db.connect()
    db.ensure_schema(conn)
    rows = analytics.player_performance(
        conn, site=a.site, cohort=a.cohort, field_band=a.field_band,
        min_tournaments=a.min_tournaments, limit=a.limit)
    if not rows:
        print("no players match the filters")
    for r in rows:
        print(f"{r['site']:<10} {r['cohort']:<12} {r['field_band'] or '?':<14} "
              f"{r['display_name']:<22} n={r['tournaments_played']:<3} "
              f"cash={r['cash_count']:<3} prize=R{r['total_prizes']:,} "
              f"cost=R{r['total_cost']:,} roi={r['roi_pct']}% "
              f"best=#{r['best_finish']}")
    conn.close()


def cmd_export(a):
    import json
    from . import analytics
    conn = db.connect()
    db.ensure_schema(conn)
    day = date.fromisoformat(a.date)
    payload = analytics.export_day(conn, day, a.site)
    text = json.dumps(payload, indent=2, default=str)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text)
        print(f"exported {day.isoformat()} -> {a.out}")
    else:
        print(text)
    conn.close()


def cmd_runs(a):
    """Recent ingestion runs (observability)."""
    conn = db.connect()
    db.ensure_schema(conn)
    s = db.schema_name()
    rows = db.query(
        conn,
        f"""SELECT run_id, site, started_at, completed_at, duration_s,
                   tournaments_discovered, tournaments_captured,
                   tournaments_failed, players_captured, hands_captured,
                   duplicates, validation_errors, status
            FROM {s}.ingestion_runs
            ORDER BY started_at DESC LIMIT %s""",
        (a.limit,))
    for r in rows:
        print(f"{r['started_at']:%Y-%m-%d %H:%M} {r['site']:<9} "
              f"status={r['status']:<10} dur={r['duration_s']}s "
              f"disc={r['tournaments_discovered']} cap={r['tournaments_captured']} "
              f"fail={r['tournaments_failed']} players={r['players_captured']} "
              f"hands={r['hands_captured']} dupes={r['duplicates']} "
              f"valerr={r['validation_errors']} run={r['run_id'][:18]}")
    conn.close()


def main(argv=None):
    p = argparse.ArgumentParser(prog="mtt", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("init-db", help="create schema + tables")
    s1.set_defaults(fn=cmd_init_db)

    s2 = sub.add_parser("ingest", help="run one capture tick for a site")
    s2.add_argument("--site", required=True, choices=["pokerbet", "sunbet"])
    s2.add_argument("--raw-dir", default="raw")
    s2.set_defaults(fn=cmd_ingest)

    s3 = sub.add_parser("daily", help="reconcile a day into daily_statistics")
    s3.add_argument("--date", default=datetime.now().date().isoformat())
    s3.add_argument("--site")
    s3.set_defaults(fn=cmd_daily)

    s4 = sub.add_parser("report", help="print daily ledger")
    s4.add_argument("--date", default=datetime.now().date().isoformat())
    s4.add_argument("--site")
    s4.set_defaults(fn=cmd_report)

    s5 = sub.add_parser("stats", help="cohort-separated DB stats")
    s5.add_argument("--site")
    s5.add_argument("--cohort")
    s5.set_defaults(fn=cmd_stats)

    s6 = sub.add_parser("analytics", help="cohort-separated player performance")
    s6.add_argument("--site")
    s6.add_argument("--cohort")
    s6.add_argument("--field-band")
    s6.add_argument("--min-tournaments", type=int, default=1)
    s6.add_argument("--limit", type=int, default=50)
    s6.set_defaults(fn=cmd_analytics)

    s7 = sub.add_parser("export", help="export a day as JSON")
    s7.add_argument("--date", default=datetime.now().date().isoformat())
    s7.add_argument("--site")
    s7.add_argument("--out", help="output file (default stdout)")
    s7.set_defaults(fn=cmd_export)

    s8 = sub.add_parser("runs", help="recent ingestion runs")
    s8.add_argument("--limit", type=int, default=10)
    s8.set_defaults(fn=cmd_runs)

    a = p.parse_args(argv)
    a.raw_dir = getattr(a, "raw_dir", "raw")
    a.fn(a)


if __name__ == "__main__":
    main()
