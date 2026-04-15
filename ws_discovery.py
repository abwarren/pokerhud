#!/usr/bin/env python3
"""
BetConstruct WebSocket Protocol Discovery
==========================================
Tries multiple protocol approaches to connect to the poker backend
and extract tournament data.

Approach 1: Socket.IO / Engine.IO
Approach 2: Raw WebSocket with binary framing
Approach 3: HTTP long-polling fallback
"""

import asyncio
import json
import time
import sys
import logging
from datetime import datetime
from pathlib import Path

import requests
import websockets

OUTPUT_DIR = Path("/opt/pokerhud/tournament_data")
OUTPUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ws_discovery")

PARTNER_ID = "18751019"
CLIENT_ID = "92311469"
PLAYER_ID = "357652843"
TOKEN = "2F90D07AC6E160842CFC8757484A5857"
CLIENT_ID_HASH = "8d96fa1aae7d4c613ab396f3677ee1e9a9bb4d75c233156a80774a462fa84a09"

WS_HOST = "poker-general.skillgames-bc.com"
GATEWAY = "sg-api.skillgames-bc.com"

all_messages = []


# ---------------------------------------------------------------------------
# Approach 1: Socket.IO handshake (Engine.IO transport)
# ---------------------------------------------------------------------------
async def try_socketio():
    """Socket.IO uses Engine.IO underneath. Try EIO=4 handshake first."""
    log.info("=" * 50)
    log.info("APPROACH 1: Socket.IO / Engine.IO")
    log.info("=" * 50)

    session = requests.Session()
    headers = {
        "Origin": "https://poker-web.pokerbet.co.za",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/146.0",
    }

    # Step 1: Engine.IO handshake via HTTP polling
    for eio_version in [4, 3]:
        for path in ["/socket.io/", "/engine.io/", "/ws/", "/", ""]:
            url = f"https://{WS_HOST}{path}"
            params = {"EIO": eio_version, "transport": "polling"}
            try:
                log.info(f"  Trying EIO={eio_version} at {url}...")
                r = session.get(url, params=params, headers=headers, timeout=10)
                log.info(f"  -> HTTP {r.status_code}: {r.text[:300]}")
                all_messages.append({
                    "approach": "socketio",
                    "url": url,
                    "eio": eio_version,
                    "status": r.status_code,
                    "response": r.text[:1000]
                })
                if r.status_code == 200:
                    return r.text
            except Exception as e:
                log.info(f"  -> {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Approach 2: Raw WebSocket with Engine.IO framing
# ---------------------------------------------------------------------------
async def try_engineio_ws():
    """Try WebSocket with Engine.IO packet framing."""
    log.info("=" * 50)
    log.info("APPROACH 2: Engine.IO WebSocket Framing")
    log.info("=" * 50)

    headers = {
        "Origin": "https://poker-web.pokerbet.co.za",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/146.0",
    }

    # Engine.IO packet types: 0=open, 1=close, 2=ping, 3=pong, 4=message, 5=upgrade, 6=noop
    # Socket.IO packet types (inside engine.io message '4'): 0=connect, 1=disconnect, 2=event, 3=ack

    for path in ["", "/socket.io/?EIO=4&transport=websocket", "/ws", "/?transport=websocket"]:
        url = f"wss://{WS_HOST}{path}"
        try:
            log.info(f"  Connecting to {url}...")
            async with websockets.connect(url, additional_headers=headers,
                                          ping_interval=None, close_timeout=3) as ws:
                log.info(f"  -> Connected!")

                # Wait for server open packet
                log.info("  -> Waiting for server packets...")
                for _ in range(5):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=3)
                        log.info(f"  <- Received: {repr(msg)[:300]}")
                        all_messages.append({"approach": "engineio_ws", "url": url, "msg": repr(msg)[:500]})

                        # Engine.IO: if server sends '0{...}', that's the open packet with sid
                        if isinstance(msg, str) and msg.startswith("0"):
                            try:
                                open_data = json.loads(msg[1:])
                                sid = open_data.get("sid")
                                log.info(f"  -> Got Engine.IO sid: {sid}")

                                # Send Socket.IO connect: 40 (EIO message type 4 + SIO connect type 0)
                                await ws.send("40")
                                log.info("  -> Sent SIO connect: 40")

                                resp = await asyncio.wait_for(ws.recv(), timeout=3)
                                log.info(f"  <- SIO connect response: {repr(resp)[:300]}")

                                # Now try sending events
                                # SIO event = 42["eventName", data]
                                events = [
                                    '42["login",{"partnerId":%s,"clientId":%s,"token":"%s"}]' % (PARTNER_ID, CLIENT_ID, TOKEN),
                                    '42["get_lobby",{"productId":3}]',
                                    '42["get_tournaments",{}]',
                                    '42["subscribe",{"channel":"tournaments"}]',
                                ]
                                for evt in events:
                                    await ws.send(evt)
                                    log.info(f"  -> Sent: {evt[:150]}")
                                    await asyncio.sleep(0.5)
                                    try:
                                        r = await asyncio.wait_for(ws.recv(), timeout=2)
                                        log.info(f"  <- Response: {repr(r)[:300]}")
                                        all_messages.append({"approach": "sio_event", "sent": evt, "received": repr(r)[:500]})
                                    except asyncio.TimeoutError:
                                        pass

                            except json.JSONDecodeError:
                                pass

                        # If response is '1' (close), the server doesn't understand us
                        if msg == "1" or msg == 1:
                            log.info("  -> Server sent close (1)")
                            break

                    except asyncio.TimeoutError:
                        break

        except Exception as e:
            log.info(f"  -> {url}: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Approach 3: BetConstruct Spring/STOMP protocol
# ---------------------------------------------------------------------------
async def try_spring_stomp():
    """BetConstruct may use Spring WebSocket with STOMP."""
    log.info("=" * 50)
    log.info("APPROACH 3: Spring STOMP")
    log.info("=" * 50)

    headers = {
        "Origin": "https://poker-web.pokerbet.co.za",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/146.0",
    }

    # STOMP connect frame
    stomp_connect = "CONNECT\naccept-version:1.1,1.0\nheart-beat:10000,10000\n\n\x00"

    url = f"wss://{WS_HOST}"
    try:
        async with websockets.connect(url, additional_headers=headers,
                                      ping_interval=None, close_timeout=3) as ws:
            log.info(f"  -> Connected to {url}")

            # Send STOMP connect
            await ws.send(stomp_connect)
            log.info("  -> Sent STOMP CONNECT")

            for _ in range(3):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3)
                    log.info(f"  <- STOMP response: {repr(msg)[:300]}")
                    all_messages.append({"approach": "stomp", "msg": repr(msg)[:500]})
                except asyncio.TimeoutError:
                    break
    except Exception as e:
        log.info(f"  -> STOMP: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Approach 4: Binary protobuf / msgpack probe
# ---------------------------------------------------------------------------
async def try_binary_protocols():
    """Try sending binary frames to discover if server expects binary protocol."""
    log.info("=" * 50)
    log.info("APPROACH 4: Binary Protocol Probe")
    log.info("=" * 50)

    headers = {
        "Origin": "https://poker-web.pokerbet.co.za",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/146.0",
    }

    url = f"wss://{WS_HOST}"
    try:
        async with websockets.connect(url, additional_headers=headers,
                                      ping_interval=None, close_timeout=3) as ws:
            log.info(f"  -> Connected to {url}")

            # Try various binary formats
            probes = [
                # Engine.IO binary ping
                b'\x02',
                # Null-terminated string
                b'{"cmd":"ping"}\x00',
                # Length-prefixed
                b'\x00\x00\x00\x0e{"cmd":"ping"}',
                # Raw text as bytes
                b'2probe',  # Engine.IO probe
                b'5',       # Engine.IO upgrade
            ]

            for probe in probes:
                try:
                    await ws.send(probe)
                    log.info(f"  -> Sent binary: {probe[:50].hex()}")
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=2)
                        log.info(f"  <- Response: {repr(msg)[:200]}")
                        all_messages.append({"approach": "binary", "sent": probe.hex(), "received": repr(msg)[:300]})
                    except asyncio.TimeoutError:
                        log.info(f"  <- No response")
                except websockets.exceptions.ConnectionClosed:
                    log.info(f"  -> Connection closed after binary probe")
                    break
    except Exception as e:
        log.info(f"  -> Binary: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Approach 5: Try the python-socketio client directly
# ---------------------------------------------------------------------------
async def try_socketio_client():
    """Use python-socketio which handles the Engine.IO handshake natively."""
    log.info("=" * 50)
    log.info("APPROACH 5: python-socketio Client")
    log.info("=" * 50)

    try:
        import socketio
    except ImportError:
        log.error("  python-socketio not installed")
        return

    received = []

    sio = socketio.AsyncClient(
        logger=True,
        engineio_logger=True,
    )

    @sio.event
    async def connect():
        log.info("  -> SIO connected!")
        received.append({"event": "connect"})

    @sio.event
    async def disconnect():
        log.info("  -> SIO disconnected")
        received.append({"event": "disconnect"})

    @sio.on("*")
    async def catch_all(event, data=None):
        log.info(f"  <- SIO event '{event}': {str(data)[:300]}")
        received.append({"event": event, "data": data})

    @sio.event
    async def connect_error(data):
        log.info(f"  -> SIO connect_error: {data}")
        received.append({"event": "connect_error", "data": str(data)})

    for base_url in [
        f"https://{WS_HOST}",
        f"wss://{WS_HOST}",
        f"https://{WS_HOST}/socket.io",
    ]:
        try:
            log.info(f"  -> Trying SIO connect to {base_url}...")
            await sio.connect(
                base_url,
                headers={"Origin": "https://poker-web.pokerbet.co.za"},
                transports=["websocket", "polling"],
                wait_timeout=10,
            )
            log.info("  -> Connected via python-socketio!")

            # Try emitting events
            try:
                await sio.emit("login", {"partnerId": int(PARTNER_ID), "clientId": int(CLIENT_ID), "token": TOKEN})
                await asyncio.sleep(2)
                await sio.emit("get_tournaments", {"partnerId": int(PARTNER_ID)})
                await asyncio.sleep(2)
                await sio.emit("get_lobby", {})
                await asyncio.sleep(3)
            except Exception as e:
                log.error(f"  -> Emit error: {e}")

            await sio.disconnect()
            break
        except Exception as e:
            log.info(f"  -> {base_url}: {type(e).__name__}: {e}")

    all_messages.extend(received)


# ---------------------------------------------------------------------------
# Approach 6: HTTP long-polling (BetConstruct fallback)
# ---------------------------------------------------------------------------
def try_http_polling():
    """BetConstruct may use HTTP long-polling for lobby data."""
    log.info("=" * 50)
    log.info("APPROACH 6: HTTP Long-Polling")
    log.info("=" * 50)

    session = requests.Session()
    headers = {
        "Origin": "https://poker-web.pokerbet.co.za",
        "Referer": "https://poker-web.pokerbet.co.za/",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/146.0",
        "Accept": "application/json, text/plain, */*",
    }

    # Try various API paths on the gateway
    endpoints = [
        f"https://{GATEWAY}/api/tournaments?partnerId={PARTNER_ID}",
        f"https://{GATEWAY}/api/lobby?partnerId={PARTNER_ID}",
        f"https://{GATEWAY}/api/v1/tournaments?partnerId={PARTNER_ID}",
        f"https://{GATEWAY}/Tournaments/?PartnerId={PARTNER_ID}&ClientId={CLIENT_ID}&format=json",
        f"https://{GATEWAY}/Lobby/?PartnerId={PARTNER_ID}&format=json",
        f"https://{GATEWAY}/TournamentSchedule/?PartnerId={PARTNER_ID}&format=json",
        f"https://{GATEWAY}/Games/?PartnerId={PARTNER_ID}&ProductId=3&format=json",
        f"https://{GATEWAY}/Tables/?PartnerId={PARTNER_ID}&format=json",
        f"https://{GATEWAY}/api/poker/tournaments",
        f"https://{GATEWAY}/api/poker/lobby",
        f"https://{WS_HOST}/api/tournaments",
        f"https://{WS_HOST}/lobby",
        # BetConstruct partner API pattern
        f"https://cmsbetconstruct.com/api/public/v1/eng/partners/{PARTNER_ID}",
        # Global hand history
        f"https://poker-hands.skillgames-bc.com/api/history?playerId={PLAYER_ID}&clientId={CLIENT_ID}",
        f"https://poker-hands.skillgames-bc.com/api/v1/hands?playerId={PLAYER_ID}",
        f"https://poker-hands.skillgames-bc.com/hands?PlayerId={PLAYER_ID}&ClientId={CLIENT_ID}&format=json",
    ]

    for url in endpoints:
        try:
            log.info(f"  GET {url}")
            r = session.get(url, headers=headers, timeout=10)
            status = r.status_code
            body = r.text[:500]
            log.info(f"  -> {status}: {body[:200]}")
            all_messages.append({"approach": "http_poll", "url": url, "status": status, "body": body})

            if status == 200 and len(r.text) > 10:
                # Save successful response
                fname = url.split("/")[-1].split("?")[0] or "response"
                path = OUTPUT_DIR / f"http_{fname}_{int(time.time())}.json"
                try:
                    data = r.json()
                    with open(path, "w") as f:
                        json.dump(data, f, indent=2)
                    log.info(f"  -> Saved to {path}")
                except:
                    with open(path, "w") as f:
                        f.write(r.text)
        except Exception as e:
            log.info(f"  -> {type(e).__name__}: {str(e)[:100]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    await try_socketio()
    await try_engineio_ws()
    await try_spring_stomp()
    await try_binary_protocols()
    await try_socketio_client()
    try_http_polling()

    # Save all discovery results
    path = OUTPUT_DIR / f"ws_discovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(path, "w") as f:
        json.dump(all_messages, f, indent=2, default=str)
    log.info(f"\nAll discovery results saved to {path}")
    log.info(f"Total messages/responses collected: {len(all_messages)}")


if __name__ == "__main__":
    asyncio.run(main())
