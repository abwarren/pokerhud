"""Security regression: no known credentials in tracked source files.

Guards the working tree only — git history still contains historical
secrets (documented in docs/security-audit.md; rotation recommended).
"""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Values that were previously hardcoded and must never return.
FORBIDDEN = [
    "Gemm@143",                              # postgres password
    "2F90D07AC6E160842CFC8757484A5857",      # BetConstruct WS token
    "8d96fa1aae7d4c613ab396f3677ee1e9a9bb4d75c233156a80774a462fa84a09",
    "357652843",                             # player id
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",  # supabase JWT prefix
]

PASSWORD_ASSIGN = re.compile(r"(password|passwd)\s*=\s*['\"][^'\"]{4,}")


def tracked_py_files():
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=REPO,
                         capture_output=True, text=True, check=True)
    return [REPO / p for p in out.stdout.splitlines() if p]


def test_no_forbidden_secret_literals():
    hits = []
    for f in tracked_py_files():
        if f.name == "test_security.py":
            continue  # this file's own FORBIDDEN list is its test data
        try:
            text = f.read_text()
        except OSError:
            continue
        for val in FORBIDDEN:
            if val in text:
                hits.append((str(f), val))
    assert hits == [], f"forbidden literals still in tracked files: {hits}"


def test_no_password_assignments_in_source():
    hits = []
    for f in tracked_py_files():
        if "test_" in f.name:
            continue
        text = f.read_text()
        for m in PASSWORD_ASSIGN.finditer(text):
            hits.append((str(f), m.group(0)))
    assert hits == [], f"password assignments in tracked source: {hits}"


def test_mtt_db_has_no_default_credentials():
    text = (REPO / "mtt" / "db.py").read_text()
    dsn_block = text[text.index("def dsn"):]
    assert "os.environ.get" in dsn_block   # credentials come from env/fallback
    assert "Gemm" not in text              # no literal password anywhere


def test_pokerbet_adapter_no_default_tokens():
    text = (REPO / "mtt" / "adapters" / "pokerbet.py").read_text()
    assert "os.environ.get(\"MTT_PB_TOKEN\")" in text
    assert "os.environ.get(\"MTT_PB_CLIENT_ID\")" in text
