#!/usr/bin/env bash
# backup_db.sh — parameterized pg_dump wrapper for the GoGaga/TechScape
# Supabase Postgres (BLK-7 mechanism; POLICY still pending — see
# scripts/BACKUP_OPTIONS.md for the one-line decision Gowtham owes).
#
# WHAT IT DOES
#   1. pg_dump the whole database in -Fc custom format (compressed,
#      selective-restore capable) into $BACKUP_DIR with a UTC timestamp.
#   2. Prune backups in $BACKUP_DIR older than $RETENTION_DAYS.
#
# ENVIRONMENT
#   DATABASE_URL      full connection string (postgresql://user:pass@host:port/db)
#                     — OR the standard PG* vars (PGHOST/PGPORT/PGUSER/
#                     PGPASSWORD/PGDATABASE), which pg_dump reads natively.
#   BACKUP_DIR        where dumps land (default: ./backups)
#   RETENTION_DAYS    REQUIRED, no default. This is the BLK-7 policy knob —
#                     the script refuses to run without an explicit value so
#                     nobody accidentally encodes a retention policy that
#                     was never decided.
#
# SUPABASE NOTE (what you need from the dashboard)
#   Supabase's pooled connection (port 6543, *.pooler.supabase.com) is NOT
#   suitable for pg_dump. Use the DIRECT connection string:
#     Dashboard -> Project Settings -> Database -> Connection string -> URI
#     (host db.<project-ref>.supabase.co, port 5432, user postgres)
#   and export it as DATABASE_URL. The database password is the one set at
#   project creation (resettable on the same page). pg_dump's major version
#   should be >= the server's (check with: pg_dump --version).
#
# EXAMPLES
#   DATABASE_URL='postgresql://postgres:...@db.abc123.supabase.co:5432/postgres' \
#     BACKUP_DIR=/var/backups/gogaga RETENTION_DAYS=14 ./scripts/backup_db.sh
#
# RESTORE (for the runbook)
#   pg_restore --clean --if-exists -d "$DATABASE_URL" <file>.dump
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"

# ── Refuse to guess retention (BLK-7 is undecided — that's the point) ──────
if [[ -z "${RETENTION_DAYS:-}" ]]; then
    echo "ERROR: RETENTION_DAYS is not set." >&2
    echo "Retention is a pending policy decision (BLK-7) — this script will" >&2
    echo "not invent one. Set it explicitly, e.g. RETENTION_DAYS=14 $0" >&2
    echo "Options for the decision: scripts/BACKUP_OPTIONS.md" >&2
    exit 2
fi
if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || [[ "$RETENTION_DAYS" -lt 1 ]]; then
    echo "ERROR: RETENTION_DAYS must be a positive integer (got: '$RETENTION_DAYS')" >&2
    exit 2
fi

# ── Connection: DATABASE_URL or PG* vars ───────────────────────────────────
if [[ -z "${DATABASE_URL:-}" && -z "${PGHOST:-}" ]]; then
    echo "ERROR: no database connection configured." >&2
    echo "Set DATABASE_URL (Supabase: Project Settings -> Database ->" >&2
    echo "Connection string -> URI, the DIRECT db.<ref>.supabase.co:5432 one," >&2
    echo "NOT the :6543 pooler) or the PGHOST/PGPORT/PGUSER/PGPASSWORD/" >&2
    echo "PGDATABASE variables." >&2
    exit 2
fi

command -v pg_dump >/dev/null 2>&1 || {
    echo "ERROR: pg_dump not found on PATH (install postgresql-client)." >&2
    exit 3
}

mkdir -p "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/gogaga_${STAMP}.dump"

echo "-> pg_dump (custom format) to $OUT"
if [[ -n "${DATABASE_URL:-}" ]]; then
    pg_dump --format=custom --no-owner --no-privileges \
            --file="$OUT" "$DATABASE_URL"
else
    pg_dump --format=custom --no-owner --no-privileges --file="$OUT"
fi

SIZE="$(du -h "$OUT" | cut -f1)"
echo "-> wrote $OUT ($SIZE)"

# ── Prune ──────────────────────────────────────────────────────────────────
echo "-> pruning *.dump older than ${RETENTION_DAYS} days in $BACKUP_DIR"
PRUNED=0
while IFS= read -r old; do
    rm -f -- "$old"
    echo "   pruned: $old"
    PRUNED=$((PRUNED + 1))
done < <(find "$BACKUP_DIR" -maxdepth 1 -name 'gogaga_*.dump' -type f \
              -mtime "+${RETENTION_DAYS}" 2>/dev/null)
echo "-> done. kept $(find "$BACKUP_DIR" -maxdepth 1 -name 'gogaga_*.dump' -type f | wc -l) dump(s), pruned ${PRUNED}."
