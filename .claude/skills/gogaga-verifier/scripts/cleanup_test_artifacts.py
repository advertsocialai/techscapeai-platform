#!/usr/bin/env python3
"""
GoGaga test-artifact cleanup — remove rows created by verification runs.

The access matrix and task-verification chains create real rows (wiki entries
titled 'matrix-test', users like *@test.local, branches named 'Matrix Test%').
Run this after an acceptance sweep to keep the dev DB clean.

SAFETY: only deletes rows matching the known test markers below. Prints what
it will delete and requires --yes to actually execute. NEVER extend the
patterns to anything that could match real data.

Usage:
  python3 cleanup_test_artifacts.py            # dry run — shows matches
  python3 cleanup_test_artifacts.py --yes      # actually delete

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (real config names)
Requires: pip install supabase
"""
import argparse
import os
import sys

try:
    from supabase import create_client
except ImportError:
    sys.exit("pip install supabase --break-system-packages (or in your venv)")

# (table, column, operator, pattern) — the ONLY things this script may touch
TEST_MARKERS = [
    ("travel_wiki", "title", "eq",   "matrix-test"),
    ("ts_users",    "email", "like", "%@test.local"),
    ("travel_franchisees", "name", "like", "Matrix Test%"),  # or travel_branches per P1 recon
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--yes", action="store_true", help="actually delete (default: dry run)")
    args = p.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not (url and key):
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")

    sb = create_client(url, key)
    total = 0

    for table, col, op, pattern in TEST_MARKERS:
        q = sb.table(table).select("id," + col)
        q = q.eq(col, pattern) if op == "eq" else q.like(col, pattern)
        try:
            rows = q.execute().data or []
        except Exception as e:
            print(f"[skip] {table}: {type(e).__name__} (table may not exist yet)")
            continue

        if not rows:
            print(f"[clean] {table}: no test rows")
            continue

        print(f"[found] {table}: {len(rows)} row(s) matching {col} {op} '{pattern}'")
        for r in rows:
            print(f"   - {r['id']}  {r.get(col, '')}")
        total += len(rows)

        if args.yes:
            d = sb.table(table).delete()
            d = d.eq(col, pattern) if op == "eq" else d.like(col, pattern)
            d.execute()
            print(f"[deleted] {table}: {len(rows)} row(s)")

    if not args.yes and total:
        print(f"\nDry run only. {total} row(s) would be deleted. Re-run with --yes.")
    elif args.yes:
        print(f"\nDone. {total} row(s) deleted.")


if __name__ == "__main__":
    main()
