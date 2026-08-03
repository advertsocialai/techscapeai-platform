#!/usr/bin/env python3
"""
Mint a short-lived GoGaga test JWT for any role — for RBAC verification
without creating real users.

IMPORTANT: Before first use, open api/app/core/security.py and confirm:
  - the signing secret env var / value  -> export as GOGAGA_JWT_SECRET
  - the algorithm (default HS256)      -> export as GOGAGA_JWT_ALG
  - the claim names the API expects (sub? user_id? email? role? branch_id? jti? type?)
If the API's claims differ from the defaults below, EDIT build_claims() to match
the API. The token must be indistinguishable from a real one.

Usage:
  python3 make_test_token.py --role viewer
  python3 make_test_token.py --role admin --branch 8f2c... --ttl 600
  python3 make_test_token.py --role super_admin --email sa@test.local

Requires: pip install pyjwt
"""
import argparse
import os
import sys
import time
import uuid

try:
    import jwt  # pyjwt
except ImportError:
    sys.exit("pip install pyjwt --break-system-packages (or in your venv)")

ROLES = ["super_admin", "admin", "agent", "viewer"]


def build_claims(args) -> dict:
    """Matches api/app/core/security.py issue_access_token EXACTLY:
    sub, biz, role, type=access, iat, exp, jti. Secret=JWT_SECRET, HS256.
    NOTE: sub must be a ts_users.id that EXISTS (require_business fetches it);
    biz must be an ACTIVE ts_businesses.id. Pass real ids via --sub/--biz."""
    now = int(time.time())
    return {
        "sub": args.sub or args.email,
        "biz": args.biz,
        "role": args.role,
        "type": "access",
        "iat": now,
        "exp": now + args.ttl,
        "jti": str(uuid.uuid4()),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--role", required=True, choices=ROLES)
    p.add_argument("--biz", required=True, help="ACTIVE ts_businesses.id uuid (required — require_business checks it)")
    p.add_argument("--sub", default=None, help="existing ts_users.id uuid (recommended; falls back to --email)")
    p.add_argument("--email", default=None, help="subject email (default role@test.local)")
    p.add_argument("--ttl", type=int, default=300, help="seconds until expiry (default 300)")
    args = p.parse_args()

    if not args.email:
        args.email = f"{args.role}@test.local"

    secret = os.environ.get("GOGAGA_JWT_SECRET")
    if not secret:
        sys.exit("Set GOGAGA_JWT_SECRET (same secret the API signs with — see core/security.py)")
    alg = os.environ.get("GOGAGA_JWT_ALG", "HS256")

    token = jwt.encode(build_claims(args), secret, algorithm=alg)
    if isinstance(token, bytes):  # pyjwt<2 compat
        token = token.decode()

    print(token)
    print(f"# role={args.role} branch={args.biz} ttl={args.ttl}s ...{token[-4:]}", file=sys.stderr)
    print(f'# use: curl -H "Authorization: Bearer $TOKEN" ...', file=sys.stderr)


if __name__ == "__main__":
    main()
