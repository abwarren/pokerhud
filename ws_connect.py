#!/usr/bin/env python3
"""
BetConstruct Skillgames WebSocket Client
==========================================
Uses the reverse-engineered backslash-delimited protocol from the
Angular poker client (main.26042fdf1e1d5bea.js).

Protocol:
  Command types: 0=pulse_request(ping), 1=pulse_response(pong), 2=event, 3=close
  Message format: cmdType + backslash + field1 + backslash + field2 ...
  Fields separated by backslash, message ends with backslash

WebSocket URL: wss://web.skillgames-bc.com:8443
Fallback URL:  wss://poker-general.skillgames-bc.com (from partner config)
"""

import asyncio
import json
import time
import logging
from datetime import datetime
from pathlib import Path

import websockets

OUTPUT_DIR = Path("/opt/pokerhud/tournament_data")
OUTPUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bc_ws")

# Protocol constants
CMD_PING = 0
CMD_PONG = 1
CMD_EVENT = 2
CMD_CLOSE = 3

# Server endpoints
WS_URLS = [
    "wss://web.skillgames-bc.com:8443",
    "wss://poker-general.skillgames-bc.com",
]

# Auth data from network trace
PARTNER_ID = "18751019"
CLIENT_ID = "92311469"
PLAYER_ID = "357652843"
TOKEN = "2F90D07AC6E160842CFC8757484A5857"

all_received = []


def build_message(cmd_type, *fields):
    """Build a BetConstruct protocol message with backslash-delimited fields."""
    parts = [str(cmd_type)]
    for f in fields:
        parts.append(str(f))
    return "\\".join(parts) + "\\"


def parse_message(raw):
    """Parse a BetConstruct protocol message into (cmd_type, fields)."""
    if not raw:
        return None, []
    parts = raw.split("\\")
    # Remove trailing empty string from final backslash
    while parts and parts[-1] == "":
        parts.pop()
    if not parts:
        return None, []
    try:
        cmd_type = int(parts[0])
    except ValueError:
        cmd_type = -1
    fields = parts[1:] if len(parts) > 1 else []
    return cmd_type, fields


async def connect_and_scrape():
    headers = {
        "Origin": "https://poker-web.pokerbet.co.za",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/146.0",
    }

    for ws_url in WS_URLS:
        log.info(f"Connecting to {ws_url}...")
        try:
            async with websockets.connect(
                ws_url,
                additional_headers=headers,
                ping_interval=None,  # We handle pings ourselves
                close_timeout=5,
                max_size=10 * 1024 * 1024,  # 10MB max message
            ) as ws:
                log.info(f"Connected to {ws_url}!")
                await handle_connection(ws)
                return  # Success, don't try other URLs
        except Exception as e:
            log.error(f"Failed to connect to {ws_url}: {type(e).__name__}: {e}")

    log.error("All WebSocket URLs failed")


async def handle_connection(ws):
    """Handle the WebSocket connection lifecycle."""

    # Phase 1: Listen for initial server messages (5s)
    log.info("Phase 1: Listening for server greeting...")
    await collect_messages(ws, duration=5, label="greeting")

    # Phase 2: Send ping to verify protocol
    log.info("Phase 2: Sending protocol ping...")
    ping_msg = build_message(CMD_PING)
    log.info(f"  -> Sending ping: {repr(ping_msg)}")
    await ws.send(ping_msg)
    await collect_messages(ws, duration=3, label="ping_response")

    # Phase 3: Send event messages (auth + lobby requests)
    log.info("Phase 3: Sending event messages...")

    # Try various event payloads
    event_payloads = [
        # Simple event with partner ID
        build_message(CMD_EVENT, PARTNER_ID),
        # Auth-style event
        build_message(CMD_EVENT, "auth", PARTNER_ID, CLIENT_ID, TOKEN, PLAYER_ID),
        # Login event
        build_message(CMD_EVENT, "login", PARTNER_ID, CLIENT_ID, TOKEN),
        # Get lobby
        build_message(CMD_EVENT, "lobby"),
        # Get tournaments
        build_message(CMD_EVENT, "tournaments"),
        # Subscribe to lobby
        build_message(CMD_EVENT, "subscribe", "lobby", PARTNER_ID),
        # Serializer-style: object type + fields
        build_message(CMD_EVENT, "product", "3", PARTNER_ID),
        # Request session
        build_message(CMD_EVENT, "session", PARTNER_ID, CLIENT_ID, "eng"),
        # Just the partner ID as event data
        build_message(CMD_EVENT, PARTNER_ID, CLIENT_ID, TOKEN),
    ]

    for i, payload in enumerate(event_payloads):
        try:
            log.info(f"  -> Event {i+1}/{len(event_payloads)}: {repr(payload[:100])}")
            await ws.send(payload)
            await collect_messages(ws, duration=2, label=f"event_{i+1}")
        except websockets.exceptions.ConnectionClosed:
            log.warning(f"  -> Connection closed after event {i+1}")
            break

    # Phase 4: Try raw field-level probing
    log.info("Phase 4: Raw field probing...")
    raw_probes = [
        # Just command type 2 with no data
        "2\\",
        # Numeric fields like IDs
        f"2\\{PARTNER_ID}\\{CLIENT_ID}\\",
        # Common BetConstruct event names from the JS
        "2\\e_connected\\",
        "2\\e_handle_command\\",
        "2\\get_products\\",
        "2\\get_tournaments\\",
        "2\\get_lobby_data\\",
        # Try with length prefix (pushBack with length mode)
        f"2\\8\\{PARTNER_ID}\\",
    ]

    for probe in raw_probes:
        try:
            log.info(f"  -> Probe: {repr(probe)}")
            await ws.send(probe)
            await collect_messages(ws, duration=1.5, label="probe")
        except websockets.exceptions.ConnectionClosed:
            log.warning("  -> Connection closed")
            break

    # Save results
    save_results()


async def collect_messages(ws, duration=5, label=""):
    """Collect and parse WebSocket messages."""
    end_time = time.time() + duration
    count = 0
    while time.time() < end_time:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(2, end_time - time.time()))
            count += 1

            if isinstance(raw, bytes):
                log.info(f"  <- [{label}] Binary ({len(raw)}b): {raw[:100].hex()}")
                entry = {
                    "label": label,
                    "type": "binary",
                    "size": len(raw),
                    "hex": raw[:500].hex(),
                    "ts": datetime.now().isoformat()
                }
            else:
                cmd_type, fields = parse_message(raw)
                cmd_names = {0: "PING", 1: "PONG", 2: "EVENT", 3: "CLOSE"}
                cmd_name = cmd_names.get(cmd_type, f"UNKNOWN({cmd_type})")

                if cmd_type == CMD_EVENT and fields:
                    log.info(f"  <- [{label}] EVENT: {fields[:5]}{'...' if len(fields) > 5 else ''}")
                    # This is tournament/lobby data!
                    entry = {
                        "label": label,
                        "type": "event",
                        "cmd": cmd_name,
                        "fields": fields,
                        "field_count": len(fields),
                        "raw": raw[:2000],
                        "ts": datetime.now().isoformat()
                    }
                elif cmd_type == CMD_PONG:
                    log.info(f"  <- [{label}] PONG")
                    entry = {"label": label, "type": "pong", "ts": datetime.now().isoformat()}
                elif cmd_type == CMD_PING:
                    log.info(f"  <- [{label}] PING - sending PONG")
                    await ws.send(build_message(CMD_PONG))
                    entry = {"label": label, "type": "ping", "ts": datetime.now().isoformat()}
                elif cmd_type == CMD_CLOSE:
                    reason = fields[0] if fields else "unknown"
                    log.info(f"  <- [{label}] CLOSE: {reason}")
                    entry = {"label": label, "type": "close", "reason": reason, "ts": datetime.now().isoformat()}
                else:
                    log.info(f"  <- [{label}] RAW: {repr(raw[:200])}")
                    entry = {"label": label, "type": "raw", "data": raw[:2000], "ts": datetime.now().isoformat()}

            all_received.append(entry)

        except asyncio.TimeoutError:
            continue
        except websockets.exceptions.ConnectionClosed:
            log.warning(f"  -> [{label}] Connection closed")
            break

    if count:
        log.info(f"  -> Collected {count} messages during '{label}'")


def save_results():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"bc_protocol_{ts}.json"
    with open(path, "w") as f:
        json.dump(all_received, f, indent=2, default=str)
    log.info(f"Results saved to {path} ({len(all_received)} messages)")

    # Print summary
    print("\n" + "=" * 60)
    print("PROTOCOL DISCOVERY SUMMARY")
    print("=" * 60)
    types = {}
    for msg in all_received:
        t = msg.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
    for t, count in sorted(types.items()):
        print(f"  {t}: {count}")

    events = [m for m in all_received if m.get("type") == "event"]
    if events:
        print(f"\nEVENT DATA ({len(events)} events):")
        for e in events[:10]:
            print(f"  Fields ({e['field_count']}): {e['fields'][:8]}")
            if e.get("raw"):
                print(f"  Raw: {e['raw'][:200]}")


if __name__ == "__main__":
    asyncio.run(connect_and_scrape())
