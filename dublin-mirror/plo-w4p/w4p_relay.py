#!/usr/bin/env python3
"""W4P Relay — reads snapshot from bot containers and POSTs to W4P Flask.
Runs on the host, independent of bot_runner. Survives bot restarts."""

import json, time, subprocess, urllib.request, urllib.error, sys, os

W4P_API = "http://172.31.17.239:5003/api/snapshot"
W4P_KEY = "trk_w4p_default"
CONTAINER = os.environ.get("W4P_CONTAINER", "bot-kele1")
INTERVAL = 2.0  # seconds
INJECT_INTERVAL = 30  # re-inject every N iterations

# Inline script that runs inside the container
INNER_SCRIPT = r"""
import json, sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
opts = Options()
opts.debugger_address = "127.0.0.1:9222"
try:
    d = webdriver.Chrome(options=opts)
    d.switch_to.default_content()
    for f in d.find_elements("tag name", "iframe"):
        if "18751019" in (f.get_attribute("src") or "") or "skillgames" in (f.get_attribute("src") or ""):
            d.switch_to.frame(f)
            break
    snap = d.execute_script("return typeof window._w4p_buildSnapshot === function ? window._w4p_buildSnapshot() : null")
    if snap:
        print(json.dumps(snap))
    else:
        print("NULL")
except Exception as e:
    print("ERR:" + str(e), file=sys.stderr)
    sys.exit(1)
"""

def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def get_snapshot():
    """Get w4p snapshot from container Chrome via docker exec."""
    try:
        result = subprocess.run(
            ["docker", "exec", CONTAINER, "python3", "-c", INNER_SCRIPT],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        out = result.stdout.strip()
        if out == "NULL" or not out:
            return None
        return json.loads(out)
    except Exception as e:
        return None

def post_snapshot(snap):
    """POST snapshot to W4P Flask."""
    data = json.dumps(snap).encode("utf-8")
    req = urllib.request.Request(
        W4P_API, data=data,
        headers={"Content-Type": "application/json", "X-API-Key": W4P_KEY},
        method="POST"
    )
    resp = urllib.request.urlopen(req, timeout=5)
    return json.loads(resp.read().decode("utf-8"))

def inject_w4p():
    """Inject w4p.js into container if not present."""
    check = subprocess.run(
        ["docker", "exec", CONTAINER, "python3", "-c",
         "from selenium import webdriver; from selenium.webdriver.chrome.options import Options; "
         "o=Options(); o.debugger_address=127.0.0.1:9222; d=webdriver.Chrome(options=o); "
         "d.switch_to.default_content(); "
         "[d.switch_to.frame(f) for f in d.find_elements(tag name,iframe) if 18751019 in (f.get_attribute(src) or )]; "
         "print(d.execute_script(return typeof window._w4p_buildSnapshot))"],
        capture_output=True, text=True, timeout=15
    )
    if "function" not in check.stdout:
        log("w4p not found in iframe, injecting...")
        subprocess.run(
            ["docker", "exec", CONTAINER, "python3", "-c",
             "from selenium import webdriver; from selenium.webdriver.chrome.options import Options; "
             "o=Options(); o.debugger_address=127.0.0.1:9222; d=webdriver.Chrome(options=o); "
             "d.switch_to.default_content(); "
             "[d.switch_to.frame(f) for f in d.find_elements(tag name,iframe) if 18751019 in (f.get_attribute(src) or )]; "
             "code=open(/tmp/w4p.js).read(); d.execute_script(code); "
             "print(injected:, d.execute_script(return typeof window._w4p_buildSnapshot))"],
            capture_output=True, text=True, timeout=15
        )

log(f"W4P relay starting for {CONTAINER}")
count = 0
errors = 0

while True:
    try:
        # Periodic re-injection check
        if count % INJECT_INTERVAL == 0:
            inject_w4p()

        snap = get_snapshot()
        if snap and snap.get("seats"):
            result = post_snapshot(snap)
            count += 1
            if count % 15 == 1:
                filled = len([s for s in snap.get("seats", []) if s.get("name") or s.get("is_hero")])
                log(f"Relay #{count}: ok={result.get(ok)}, filled_seats={filled}")
            errors = 0
        else:
            errors += 1
            if errors % 15 == 1:
                log(f"No snapshot (attempt {errors})")

    except Exception as e:
        errors += 1
        if errors % 15 == 1:
            log(f"Error ({errors}): {e}")

    time.sleep(INTERVAL)
