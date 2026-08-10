---
name: gogaga-scoreboard
description: Keeps GOGAGA_ANALYSIS_REPORT.md (the combined completeness scoreboard for both apps) true in every commit. ALWAYS use this skill in EVERY session that commits any change to this repo — read it at session start alongside gogaga-backend/gogaga-migrations/gogaga-verifier. Trigger on any commit, score, percentage, completeness, blocker (BLK-*), stub-to-live transition, or mention of the scoreboard/analysis report. Any commit that moves an area's completeness must update GOGAGA_ANALYSIS_REPORT.md in the SAME commit; deliberate no-ops say "no scoreboard impact" in the commit message.
---

# gogaga-scoreboard — keep GOGAGA_ANALYSIS_REPORT.md true, always

## When this skill applies
EVERY session that commits any change to this repo. Read this skill at session start
alongside gogaga-backend/gogaga-migrations/gogaga-verifier. This is not an optional
reporting nicety — the scoreboard is the project's single source of truth for state,
and a stale scoreboard is worse than none because it gets believed.

## The one rule
**Any commit that moves an area's completeness — up OR down — must update
`GOGAGA_ANALYSIS_REPORT.md` in the SAME commit.** Down-moves matter as much as
up-moves: a regression that silently leaves an old higher score in place is a lie.

## What counts as "moves an area"
- Adding/completing/fixing anything in a scored area (the 14 rows: DB, Backend, UI,
  Auth, Validation, Backend testing, Frontend testing, Rate limiting, Deployment,
  CI/CD, Observability, Accessibility, Compliance, Docs/secrets — per app where the
  table splits Dashboard vs Customer app)
- Breaking or regressing anything in a scored area (tests newly failing, an endpoint
  removed, a deploy going red)
- Resolving or adding any blocker (BLK-*) — update the Blocker index line AND any row
  whose "What's missing / blocker" column references it AND flip the corresponding
  row in BLOCKERS.md
- Changing a stub to live (or live to stub) — update the Live-verified column AND the
  "Stubbed vs live — the seams" table
- Pure refactors/docs changes that move no score: no scoreboard change needed, but
  state that explicitly in the commit message ("no scoreboard impact") so the
  safety-net check (below) can distinguish deliberate no-ops from forgotten updates.

## How to update (mechanics)
1. Update the affected row(s): the percentage, the Live-verified marker, and the
   "What's missing / blocker" text so it describes what's missing NOW, not what was
   missing before your change.
2. Update the "Last updated" line: date + the commit context this update ships in.
   Repo convention (set by the file's own history): reference the SHA of the state
   being described — the previous HEAD — plus a short run label, e.g.
   `Last updated: **2026-08-09** at `21d4775` (push-to-100% run)`.
3. If your change affects the built-vs-live caveat at the top (e.g. BLK-2/BLK-3
   resolved and data HAS now travelled Postgres→screen), rewrite that caveat — it is
   the single most important sentence in the file and must never be stale.
4. Keep score honesty absolute: "built and verified by construction" vs
   "live-verified" are different claims — never upgrade a number to Live without
   real evidence from this session, and never let a stub's completion masquerade as
   live in the percentage alone.
5. Cross-file consistency: PLATFORM_STATUS.md holds narrative evidence,
   COMPLIANCE_CHECKLIST.md holds compliance detail, BLOCKERS.md holds blocker rows —
   if your change touches their domains, update them in the same commit too. The
   scoreboard references them; they must not contradict it.

## Scoring discipline (so numbers stay comparable across sessions)
- Percentages are area-completeness against the CURRENT agreed scope, not against
  aspiration — if scope legitimately grows (new requirement), a score MAY go down
  with an explanatory note; that's honest, not a failure.
- Never move a score more than the evidence supports. A 5-point move needs a named
  reason in the "What's missing" column diff; a 20-point move needs real evidence
  cited (test output, deploy status, probe result).
- The Live-verified column only shows ✅ with evidence produced in a real session
  (deploy green, rows actually served, real audio transmitted) — construction-only
  verification stays ❌/⚠️ no matter how thorough.

## Mechanical safety net
`scripts/check_scoreboard_updated.sh` fails when a commit touches scoring-relevant
paths without touching the report and without "no scoreboard impact" in its message.
It runs as the `Scoreboard Check` job in CI (live once BLK-5/Actions billing is
resolved) and can be run locally: `scripts/check_scoreboard_updated.sh [<commit>]`.
It is a nudge, not an unbypassable gate — the escape hatch string is deliberate and
its presence in history is itself auditable.

## Session-end checklist (run before your final commit of any session)
- [ ] Did any commit this session move any area? → scoreboard updated in those commits?
- [ ] Any BLK-* resolved/added? → Blocker index + affected rows + BLOCKERS.md all consistent?
- [ ] Stub↔live transitions? → seams table updated?
- [ ] "Last updated" line current?
- [ ] Top caveat still true?
