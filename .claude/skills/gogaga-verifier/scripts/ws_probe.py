#!/usr/bin/env python3
"""
GoGaga WebSocket probe — verify the live call feed (Phase 2+).

Connects to /ws/calls/{call_id}, prints every message with a timestamp for
--duration seconds (default 30), then reports message counts by type.

AUTH CHANNEL — READ THIS
------------------------
This probe USED to authenticate only via `additional_headers`, a Python-client
capability with no browser equivalent. That is precisely why the endpoint
stayed unusable from browsers without anyone noticing: the verification tool
could not have caught it. A probe that exercises only a channel real clients
cannot use is worse than no probe — it manufactures false confidence.

It now defaults to `--auth subprotocol`, the SAME channel the dashboard uses
(`['bearer', <jwt>]`). Use `--auth header` for the legacy path.

Usage:
  python3 ws_probe.py --call-id <uuid> --token $TOKEN
  python3 ws_probe.py --call-id <uuid> --token $TOKEN --auth header
  python3 ws_probe.py --call-id <uuid> --token $TOKEN --duration 60

Env: GOGAGA_API (http base; ws derived), or --url to override entirely.
Requires: pip install websockets
"""
import argparse
import asyncio
import json
import os
import sys
import time

try:
    import websockets
except ImportError:
    sys.exit("pip install websockets --break-system-packages (or in your venv)")


# Types the backend actually publishes. Anything else is a spec artefact —
# see api-conventions.md, corrected 2026-08-08.
EMITTED = {"transcript", "call_status", "sentiment", "suggestion", "takeover_state"}
NEVER_EMITTED = {"whisper", "speaking", "intent", "event", "extraction", "summary"}


def _connect_kwargs(token: str | None, auth: str) -> dict:
    """Auth channel, matched to what a real client can actually do."""
    if not token:
        return {}
    if auth == "header":
        # Python-only. A browser CANNOT do this — that is the whole lesson here.
        return {"additional_headers": {"Authorization": f"Bearer {token}"}}
    # Browser-shaped, and the default: exactly what agency-dashboard sends.
    return {"subprotocols": ["bearer", token]}


async def probe(url: str, token: str | None, duration: int, auth: str = "subprotocol"):
    counts: dict[str, int] = {}
    start = time.time()
    print(f"Connecting: {url} (for {duration}s, auth={auth})")
    try:
        async with websockets.connect(url, **_connect_kwargs(token, auth)) as ws:
            echoed = getattr(ws, "subprotocol", None)
            print(f"CONNECTED (subprotocol echoed: {echoed!r})")
            if auth == "subprotocol" and echoed != "bearer":
                # A real browser would drop this connection silently.
                print("  WARNING: server did NOT echo 'bearer' — a browser would drop this")
            while time.time() - start < duration:
                try:
                    remaining = duration - (time.time() - start)
                    msg = await asyncio.wait_for(ws.recv(), timeout=max(remaining, 0.1))
                except asyncio.TimeoutError:
                    break
                ts = time.strftime("%H:%M:%S")
                try:
                    data = json.loads(msg)
                    mtype = data.get("type", "unknown")
                except (json.JSONDecodeError, AttributeError):
                    data, mtype = msg, "raw"
                counts[mtype] = counts.get(mtype, 0) + 1
                preview = str(data)[:160]
                print(f"[{ts}] {mtype}: {preview}")
    except Exception as e:
        print(f"CONNECTION FAILED: {type(e).__name__}: {e}")
        sys.exit(1)

    print("\n== Summary ==")
    if not counts:
        print("No messages received — feed may be silent or call inactive.")
        sys.exit(2)
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--call-id", required=False)
    p.add_argument("--token", default=os.environ.get("GOGAGA_WS_TOKEN"))
    p.add_argument("--duration", type=int, default=30)
    p.add_argument("--url", default=None, help="full ws:// url override")
    p.add_argument("--auth", choices=["subprotocol", "header"], default="subprotocol",
                   help="subprotocol (default, browser-shaped) | header (Python-only, legacy)")
    args = p.parse_args()

    if args.url:
        url = args.url
    else:
        if not args.call_id:
            sys.exit("--call-id required (or pass --url)")
        api = os.environ.get("GOGAGA_API", "http://localhost:8000")
        url = api.replace("http://", "ws://").replace("https://", "wss://")
        url = f"{url}/ws/calls/{args.call_id}"

    asyncio.run(probe(url, args.token, args.duration, args.auth))


if __name__ == "__main__":
    main()
