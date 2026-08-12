"""Inventory of PG databases on localhost:5432 and schemas inside pokerhud — read-only."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "projects/poker/pokerhud"))
from mtt import db  # noqa: E402

conn = db.connect()
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database WHERE NOT datistemplate ORDER BY 1")
print("DATABASES:")
for r in cur.fetchall():
    print(f"  {r[0]:20s} {r[1]}")
cur.execute("SELECT table_schema, count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') GROUP BY 1 ORDER BY 1")
print("POKERHUD DB SCHEMAS:")
for r in cur.fetchall():
    print(f"  {r[0]:20s} {r[1]} tables")
conn.close()
