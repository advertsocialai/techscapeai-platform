# Backup policy — the one-line decision (BLK-7)

The MECHANISM is done (`scripts/backup_db.sh`, a pg_dump wrapper with an
explicit retention knob). What is still missing is the POLICY. Pick one
letter and a number of days; reply "Option B, 14 days" (or similar) and
BLK-7 closes.

| | What | Effort | Cost | Caveats |
|---|---|---|---|---|
| **A** | Rely on Supabase's built-in daily backups / PITR | Zero — verify only | Included in Pro plan and up (PITR is a paid add-on) | **Verify the project's plan tier actually includes it** — Free tier has NO backups. Restore granularity/window is whatever the plan gives; no off-Supabase copy, so a Supabase account problem takes the backups with it |
| **B** | Nightly `scripts/backup_db.sh` (cron on any machine with the direct DB connection string), retention N days | ~30 min: put the direct connection string (dashboard → Project Settings → Database → URI, port 5432 NOT the 6543 pooler) on a box, add one cron line | Disk only (dumps are compressed; current DB is small) | Off-platform copy you control; restore tested with `pg_restore`. Needs a machine that's actually on at night and dump files treated as sensitive (they contain all PII) |
| **C** | Both A and B | A's verification + B's 30 min | Sum of both | Belt and braces: platform-level PITR for fat-finger recovery, plus an independent copy for provider-level disasters. Recommended once real customer calls/payments flow |

Example cron for B (nightly 02:30 IST = 21:00 UTC):

```
0 21 * * * DATABASE_URL='postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres' BACKUP_DIR=/var/backups/gogaga RETENTION_DAYS=14 /path/to/repo/scripts/backup_db.sh >> /var/log/gogaga-backup.log 2>&1
```

Decision also feeds C-4 (recording retention) and the privacy policy's
retention section — same number, decided once.
