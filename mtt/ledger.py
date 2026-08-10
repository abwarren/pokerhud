"""Daily reconciliation + report.

For a given date (Africa/Johannesburg day boundary):
- expected   = tournaments discovered for that day (in DB, start_time::date = day)
- captured   = tournaments with a lifecycle snapshot or completed status
- complete   = data_quality_score >= 90
- partial    = 60 <= score < 90
- missing    = expected - captured (never silently assumed: expected is
  what the source actually advertised, so a missing row is a real gap)

Writes daily_statistics per (date, site, cohort). R1000 cohort rows are
kept separate — the report always shows them isolated.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db, quality

SA = ZoneInfo("Africa/Johannesburg")


def sa_day_bounds(day: date) -> tuple[datetime, datetime]:
    """UTC instants for the SAST day [00:00, 24:00)."""
    start = datetime.combine(day, time.min, tzinfo=SA).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def day_from_utc(ts) -> date:
    return ts.astimezone(SA).date()


def reconcile(conn, day: date, site: str | None = None) -> dict:
    """Compute per-cohort counts for a day and persist daily_statistics."""
    start, end = sa_day_bounds(day)
    s = db.schema_name()
    rows = db.query(
        conn,
        f"""SELECT site, cohort, COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                   COUNT(*) FILTER (WHERE data_quality_score >= 90) AS complete,
                   COUNT(*) FILTER (WHERE data_quality_score >= 60 AND data_quality_score < 90) AS partial,
                   COUNT(*) FILTER (WHERE data_quality_score < 60) AS incomplete,
                   COALESCE(SUM(entries), 0) AS entries_total,
                   COALESCE(SUM(prize_pool), 0) AS prize_pool_total
            FROM {s}.tournaments
            WHERE start_time >= %s AND start_time < %s
              AND cohort IS NOT NULL
              AND (%s::text IS NULL OR site = %s)
            GROUP BY site, cohort
            ORDER BY site, cohort""",
        (start, end, site, site))

    report = {}
    for r in rows:
        captured = r["total"] - r["incomplete"]
        if r["completed"]:
            captured = max(captured, r["completed"])
        counts = {
            "expected": r["total"],
            "captured": captured,
            "complete": r["complete"],
            "partial": r["partial"],
            "missing": r["total"] - captured,
            "entries_total": r["entries_total"],
            "prize_pool_total": r["prize_pool_total"],
        }
        key = (r["site"], r["cohort"])
        report[key] = counts
        db.upsert_daily_stat(conn, day, r["site"], r["cohort"], counts)
    return report


def render_report(report: dict, day: date) -> str:
    lines = [f"DAILY TOURNAMENT LEDGER — {day.isoformat()} (SAST)",
             "=" * 62]
    totals = {}
    for (site, cohort), c in sorted(report.items()):
        key = site
        t = totals.setdefault(key, dict(expected=0, captured=0, complete=0,
                                        partial=0, missing=0, entries=0, prize=0))
        for k, v in (("expected", c["expected"]), ("captured", c["captured"]),
                     ("complete", c["complete"]), ("partial", c["partial"]),
                     ("missing", c["missing"])):
            t[k] += v
        t["entries"] += c["entries_total"]
        t["prize"] += c["prize_pool_total"]
        lines.append(f"\n{site.upper()} / {cohort}")
        lines.append(f"  expected={c['expected']:<4} captured={c['captured']:<4} "
                     f"complete={c['complete']:<4} partial={c['partial']:<4} "
                     f"missing={c['missing']:<4} entries={c['entries_total']:<7} "
                     f"prize=R{c['prize_pool_total']:,}")
    lines.append("\n" + "-" * 62)
    for site, t in sorted(totals.items()):
        lines.append(f"{site.upper()} TOTAL: expected={t['expected']} captured={t['captured']} "
                     f"complete={t['complete']} partial={t['partial']} missing={t['missing']} "
                     f"entries={t['entries']} prize=R{t['prize']:,}")
    return "\n".join(lines)
