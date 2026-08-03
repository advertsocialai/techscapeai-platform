#!/usr/bin/env python3
"""
Replay a recorded Plivo media-stream session into the local WS endpoint —
iterate on STT/AI/TTS without making real phone calls.

RECORDING (do once, during T3 with a real call): log every raw WS message
your /webhook/stream endpoint receives to a JSONL file, one JSON object per
line, in arrival order, e.g.
    {"t": 0.000, "msg": {"event": "start", ...}}
    {"t": 0.020, "msg": {"event": "media", "media": {"payload": "<b64>"}}}
    ...
    {"t": 41.3,  "msg": {"event": "stop", ...}}
(`t` = seconds since first message; used to reproduce original pacing.)

REPLAY:
  python3 replay_stream.py --file call1.jsonl --url ws://localhost:8000/api/travel/webhook/stream
  python3 replay_stream.py --file call1.jsonl --speed 2.0     # 2x faster
  python3 replay_stream.py --file call1.jsonl --no-timing     # firehose

The endpoint should treat this exactly like Plivo. If it validates something
per-connection (headers, tokens), add them below where marked.

Requires: pip install websockets
"""
import argparse
import asyncio
import json
import sys
import time

try:
    import websockets
except ImportError:
    sys.exit("pip install websockets --break-system-packages (or in your venv)")


async def replay(path: str, url: str, speed: float, use_timing: bool):
    lines = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                lines.append(json.loads(ln))
    if not lines:
        sys.exit("empty recording")

    print(f"Replaying {len(lines)} messages → {url} (speed x{speed})")
    # If your endpoint needs headers (auth, etc.) add: additional_headers={...}
    async with websockets.connect(url) as ws:
        t0 = time.time()
        base = lines[0].get("t", 0.0)
        sent = 0
        for item in lines:
            if use_timing:
                target = (item.get("t", 0.0) - base) / speed
                delay = target - (time.time() - t0)
                if delay > 0:
                    await asyncio.sleep(delay)
            await ws.send(json.dumps(item["msg"]))
            sent += 1
            ev = item["msg"].get("event", "?")
            if ev != "media" or sent % 50 == 0:
                print(f"  [{sent}/{len(lines)}] {ev}")
        # give the server a moment to flush transcripts before closing
        await asyncio.sleep(2)
    print("Replay complete. Now check: travel_transcripts rows + VOICE_TURN log lines.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="JSONL recording")
    p.add_argument("--url", required=True, help="ws://.../webhook/stream")
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--no-timing", action="store_true", help="ignore recorded pacing")
    a = p.parse_args()
    asyncio.run(replay(a.file, a.url, a.speed, not a.no_timing))


if __name__ == "__main__":
    main()
