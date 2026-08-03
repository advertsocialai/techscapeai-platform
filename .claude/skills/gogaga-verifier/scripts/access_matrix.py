#!/usr/bin/env python3
"""
GoGaga access matrix runner — every endpoint x every role, expected vs actual.

Reads a spec JSON (see references/matrix-spec.json), mints a short-lived token
per role via make_test_token.py, hits each endpoint, and prints a PASS/FAIL
table. Exits non-zero if any cell mismatches — suitable for the phase
acceptance sweep and CI.

IMPORTANT (found the hard way in P1): this repo's RBAC is DB-row-based, not
token-claim-based. `core/deps.py`'s `get_current_user` re-fetches the real
ts_users row by the token's `sub` claim and authorizes on THAT row's actual
`role` column — the token's own `role` claim is not read for authorization.
So minting a token with `--role super_admin` but no real `--sub`/`--biz`
either fails outright (no active business/user to resolve) or, worse,
silently tests the wrong role. You MUST have one real ts_users row per
role, in an ACTIVE ts_businesses, before running this script. The "admin"
test identity below corresponds to a row stored with role='manager' (see
core/deps.py's docstring for why bare 'admin' means something else here).

Setup (one-time per test run — see PHASE1_REPORT.md for a full worked
example): register a test business via POST /auth/register-business, then
create one user per role via POST /users (role: super_admin, manager,
agent, viewer), then export their real ids:
  export GOGAGA_TEST_BIZ=<business id>
  export GOGAGA_SUB_SUPER_ADMIN=<super_admin user id>
  export GOGAGA_SUB_ADMIN=<manager-role user id — this IS the "admin" column>
  export GOGAGA_SUB_AGENT=<agent-role user id>
  export GOGAGA_SUB_VIEWER=<viewer-role user id>

Usage:
  python3 access_matrix.py --spec ../references/matrix-spec.json
  python3 access_matrix.py --spec ../references/matrix-spec.json --only /api/v1/users

Env: GOGAGA_API (default http://localhost:8000), GOGAGA_JWT_SECRET, GOGAGA_JWT_ALG,
     GOGAGA_TEST_BIZ, GOGAGA_SUB_SUPER_ADMIN, GOGAGA_SUB_ADMIN, GOGAGA_SUB_AGENT, GOGAGA_SUB_VIEWER
Requires: pip install pyjwt requests (project venv — system python3 may lack pyjwt)
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("pip install requests --break-system-packages (or in your venv)")

ROLES = ["super_admin", "admin", "agent", "viewer"]
_SUB_ENV = {
    "super_admin": "GOGAGA_SUB_SUPER_ADMIN",
    "admin":       "GOGAGA_SUB_ADMIN",   # stored as role='manager' — see docstring
    "agent":       "GOGAGA_SUB_AGENT",
    "viewer":      "GOGAGA_SUB_VIEWER",
}
HERE = Path(__file__).parent


def mint(role: str) -> str:
    biz = os.environ.get("GOGAGA_TEST_BIZ")
    sub = os.environ.get(_SUB_ENV[role])
    if not biz or not sub:
        sys.exit(
            f"Missing {_SUB_ENV[role]} and/or GOGAGA_TEST_BIZ for role={role}. "
            "This repo's RBAC reads the real DB row, not the token claim — "
            "you need a real per-role test user first. See this script's "
            "module docstring for the one-time setup sequence."
        )
    out = subprocess.run(
        [sys.executable, str(HERE / "make_test_token.py"),
         "--role", role, "--biz", biz, "--sub", sub, "--ttl", "600"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.exit(f"token mint failed for {role}: {out.stderr.strip()}")
    return out.stdout.strip().splitlines()[0]


def call(api, method, path, token, body):
    url = api + path
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        r = requests.request(method, url, headers=headers, json=body, timeout=10)
        return r.status_code
    except requests.RequestException as e:
        return f"ERR:{type(e).__name__}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--spec", required=True)
    p.add_argument("--only", default=None, help="filter: only paths containing this substring")
    args = p.parse_args()

    api = os.environ.get("GOGAGA_API", "http://localhost:8000")
    spec = json.loads(Path(args.spec).read_text())

    tokens = {r: mint(r) for r in ROLES}
    print(f"Minted tokens for {len(tokens)} roles. Target: {api}\n")

    failures = 0
    header = f"{'METHOD':7} {'PATH':42} " + " ".join(f"{r:>12}" for r in ROLES)
    print(header)
    print("-" * len(header))

    for ep in spec["endpoints"]:
        if args.only and args.only not in ep["path"]:
            continue
        row = f"{ep['method']:7} {ep['path']:42} "
        for role in ROLES:
            expected = ep["expect"][role]
            actual = call(api, ep["method"], ep["path"], tokens[role], ep.get("body"))
            ok = (actual == expected)
            if not ok:
                failures += 1
            mark = "PASS" if ok else "FAIL"
            row += f" {str(actual):>4}/{expected:<3}{mark[0]:>3}"
        print(row)

    print()
    if failures:
        print(f"ACCESS MATRIX: {failures} FAILURE(S)")
        sys.exit(1)
    print("ACCESS MATRIX: ALL PASS")


if __name__ == "__main__":
    main()
