#!/usr/bin/env python3
"""Single-process entrypoint for the merged pokerhud app (port 8899).

Owns the PID lock; loads persisted state and starts background threads AFTER
the app exists (never at import). Stale-PID aware; removes PID file on exit.
"""

import atexit
import os
import signal
import sys
from pathlib import Path

PID_FILE = Path(os.getenv("PID_FILE", "/tmp/pokerhud-app.pid"))
PORT = int(os.getenv("PORT", "8899"))


def acquire_pid() -> None:
    if PID_FILE.exists():
        try:
            os.kill(int(PID_FILE.read_text().strip()), 0)
            sys.exit(f"already running (pid {PID_FILE.read_text().strip()})")
        except (ProcessLookupError, ValueError):
            pass  # stale pid — reclaim
    PID_FILE.write_text(str(os.getpid()))
    atexit.register(lambda: PID_FILE.unlink(missing_ok=True))


def _graceful(signum, frame):
    sys.exit(0)


from webapp import create_app  # noqa: E402
from webapp.remote_bp import start_background  # noqa: E402

acquire_pid()
signal.signal(signal.SIGTERM, _graceful)
signal.signal(signal.SIGINT, _graceful)

app = create_app()
start_background(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
