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

    a = p.parse_args(argv)
    a.raw_dir = getattr(a, "raw_dir", "raw")
    a.fn(a)


if __name__ == "__main__":
    main()
