#!/usr/bin/env python3
"""
Parse VOICE_TURN log lines and assert the latency budget.

Line format (exact, per gogaga-backend/references/api-conventions.md):
VOICE_TURN call_id=<uuid> seq=<n> stt_ms=<int> llm_ttft_ms=<int> llm_total_ms=<int> tts_ttfb_ms=<int> total_ms=<int> engine=<sarvam|deepgram> lang=<te|en|hi>

Usage:
  grep VOICE_TURN api.log | python3 latency_check.py
  python3 latency_check.py --file api.log --median-max 1100 --p95-max 1400
Exit 0 = within budget; 1 = over; 2 = no data.
"""
import argparse
import re
import statistics
import sys

PAT = re.compile(
    r"VOICE_TURN .*?stt_ms=(\d+) llm_ttft_ms=(\d+) llm_total_ms=(\d+) "
    r"tts_ttfb_ms=(\d+) total_ms=(\d+) engine=(\w+) lang=(\w+)"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None, help="log file (default: stdin)")
    ap.add_argument("--median-max", type=int, default=1100)
    ap.add_argument("--p95-max", type=int, default=1400)
    a = ap.parse_args()

    src = open(a.file) if a.file else sys.stdin
    rows = [tuple(map(str, m.groups())) for line in src if (m := PAT.search(line))]
    if a.file:
        src.close()
    if not rows:
        print("No VOICE_TURN lines found.")
        sys.exit(2)

    cols = ["stt_ms", "llm_ttft_ms", "llm_total_ms", "tts_ttfb_ms", "total_ms"]
    print(f"turns: {len(rows)}")
    print(f"{'hop':14} {'median':>8} {'p95':>8} {'max':>8}")
    totals = []
    for i, name in enumerate(cols):
        vals = sorted(int(r[i]) for r in rows)
        med = statistics.median(vals)
        p95 = vals[max(0, int(len(vals) * 0.95) - 1)]
        print(f"{name:14} {med:8.0f} {p95:8.0f} {vals[-1]:8d}")
        if name == "total_ms":
            totals = (med, p95)

    by_engine = {}
    for r in rows:
        by_engine.setdefault(r[5], []).append(int(r[4]))
    for eng, vals in by_engine.items():
        print(f"  engine={eng}: n={len(vals)} median_total={statistics.median(vals):.0f}")

    med, p95 = totals
    ok = med <= a.median_max and p95 <= a.p95_max
    print(f"\nBudget: median<={a.median_max} p95<={a.p95_max} → {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
