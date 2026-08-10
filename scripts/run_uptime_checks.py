#!/usr/bin/env python3
"""
Execute scripts/uptime_checks.yaml locally (or from any CI cron).

  python3 scripts/run_uptime_checks.py                 # run every live check
  python3 scripts/run_uptime_checks.py --only api-health
  UPTIME_API_HEALTH_URL=http://localhost:8000/api/health \
      python3 scripts/run_uptime_checks.py             # point a check elsewhere

Exit codes: 0 = every executed check passed (skips are fine, but all-skipped
prints a loud warning), 1 = at least one check failed, 2 = config problem.

Checks marked `placeholder: true` (no live URL yet — deploys blocked on the
Vercel Root Directory clicks, see scripts/DEPLOY_READINESS.md) are SKIPPED
unless their `url_env` variable supplies a real URL. That keeps this script
green in CI today and makes it fail honestly the day real URLs exist and stop
answering.

Dependencies: httpx (already in api/requirements.txt) and PyYAML.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required (pip install httpx — it is already in "
          "api/requirements.txt)", file=sys.stderr)
    sys.exit(2)

DEFAULT_FILE = Path(__file__).resolve().parent / "uptime_checks.yaml"
FALLBACK_DEFAULTS = {"method": "GET", "expected_status": 200, "timeout_seconds": 10}


def load_checks(path: Path) -> list[dict]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        print(f"ERROR: cannot load {path}: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(doc, dict) or not isinstance(doc.get("checks"), list):
        print(f"ERROR: {path} must be a mapping with a 'checks' list", file=sys.stderr)
        sys.exit(2)
    defaults = {**FALLBACK_DEFAULTS, **(doc.get("defaults") or {})}
    checks = []
    for i, raw in enumerate(doc["checks"]):
        if not isinstance(raw, dict) or "id" not in raw or "url" not in raw:
            print(f"ERROR: checks[{i}] needs at least 'id' and 'url'", file=sys.stderr)
            sys.exit(2)
        checks.append({**defaults, **raw})
    ids = [c["id"] for c in checks]
    if len(ids) != len(set(ids)):
        print("ERROR: duplicate check ids", file=sys.stderr)
        sys.exit(2)
    return checks


def run_check(check: dict) -> tuple[str, str]:
    """Returns (status, detail) where status is PASS | FAIL | SKIP."""
    url = check["url"]
    env_name = check.get("url_env")
    override = os.environ.get(env_name, "").strip() if env_name else ""
    if override:
        url = override
    elif check.get("placeholder"):
        return "SKIP", f"placeholder URL — set {env_name or 'a url_env'} to run"

    method = str(check["method"]).upper()
    expected = int(check["expected_status"])
    timeout = float(check["timeout_seconds"])
    try:
        r = httpx.request(method, url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as e:
        return "FAIL", f"{method} {url} -> {type(e).__name__}: {e}"
    if r.status_code != expected:
        return "FAIL", f"{method} {url} -> {r.status_code} (expected {expected})"
    ms = int(r.elapsed.total_seconds() * 1000)
    return "PASS", f"{method} {url} -> {r.status_code} in {ms}ms"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE,
                    help=f"checks file (default: {DEFAULT_FILE})")
    ap.add_argument("--only", action="append", metavar="ID",
                    help="run only this check id (repeatable)")
    args = ap.parse_args()

    checks = load_checks(args.file)
    if args.only:
        unknown = set(args.only) - {c["id"] for c in checks}
        if unknown:
            print(f"ERROR: unknown check id(s): {', '.join(sorted(unknown))}",
                  file=sys.stderr)
            return 2
        checks = [c for c in checks if c["id"] in args.only]

    failures = 0
    executed = 0
    for check in checks:
        status, detail = run_check(check)
        print(f"[{status}] {check['id']:<18} {detail}")
        if status == "FAIL":
            failures += 1
        if status != "SKIP":
            executed += 1

    print(f"\n{executed} executed, {failures} failed, "
          f"{len(checks) - executed} skipped (of {len(checks)})")
    if failures:
        return 1
    if executed == 0:
        print("WARNING: every check was skipped — no live URLs configured yet. "
              "This run proved nothing about uptime.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
