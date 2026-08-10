"""Test bootstrap: isolated mtt_test schema, fixture loaders."""

import os

os.environ.setdefault("MTT_SCHEMA", "mtt_test")
os.environ.setdefault("MTT_RAW_DIR", "/tmp/mtt_test_raw")

import pytest

from mtt import db


@pytest.fixture(scope="session", autouse=True)
def fresh_test_schema():
    """Drop + recreate mtt_test once per session so DDL changes apply."""
    conn = db.connect()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {db.schema_name()} CASCADE")
    conn.close()
    conn = db.connect()
    db.ensure_schema(conn)
    conn.close()
    yield
