#!/usr/bin/env python3
"""
GoGaga WebSocket probe — verify the live call feed (Phase 2+).

Connects to /ws/calls/{call_id}, prints every message with a timestamp for
--duration seconds (default 30), then reports message counts by type
(transcript / whisper / other). Use during a real or simulated call to prove
the dashboard feed works before any frontend exists.

Usage:
  python3 ws_probe.py --call-id <uuid>
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


async def probe(url: str, token: str | None, duration: int):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    counts: dict[str, int] = {}
    start = time.time()
    print(f"Connecting: {url} (for {duration}s)")
    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            print("CONNECTED")
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
    args = p.parse_args()

    if args.url:
        url = args.url
    else:
        if not args.call_id:
            sys.exit("--call-id required (or pass --url)")
        api = os.environ.get("GOGAGA_API", "http://localhost:8000")
        url = api.replace("http://", "ws://").replace("https://", "wss://")
        url = f"{url}/ws/calls/{args.call_id}"

    asyncio.run(probe(url, args.token, args.duration))


if __name__ == "__main__":
    main()
