---
name: gogaga-golive-roadmap
description: Keeps GO_LIVE_ROADMAP.md (the dependency-ordered Phase 0-10 path from every stub to live) accurate on every change. ALWAYS use this skill in EVERY session that commits any change to this repo — read GO_LIVE_ROADMAP.md at session start alongside gogaga-backend/gogaga-migrations/gogaga-verifier/gogaga-scoreboard, to know what phase the project is actually in before doing anything else. Trigger on any mention of a blocker ID (BLK-*, B-<phase>-<n>, DEBT-*), phase gate, "what's next", "go live", "unblock", or a commit that touches BLOCKERS.md. A commit that closes a roadmap step or resolves a referenced blocker must update GO_LIVE_ROADMAP.md in the same commit; genuine no-ops say "no roadmap impact" in the commit message.
---

# gogaga-golive-roadmap — keep the dependency-ordered path to live accurate

## When this skill applies
Every session, loaded alongside `gogaga-backend`/`gogaga-migrations`/`gogaga-verifier`/
`gogaga-scoreboard`. Read `GO_LIVE_ROADMAP.md` at session start to know what phase the
project is actually in before doing anything else this session.

## What this file is, precisely
- `GOGAGA_ANALYSIS_REPORT.md` = the score, flat, per-area.
- `BLOCKERS.md` = the ledger, flat, 60+ IDs, no order.
- `GO_LIVE_ROADMAP.md` = the **sequence** — every pending item grouped into
  dependency-ordered phases (0–10), each phase stating exactly what to do and what
  it unlocks. This file does not duplicate numbers from the other two; it
  **sequences them by reference** (blocker IDs, area names) — never restate a score
  or blocker detail here that could drift out of sync with its source of truth.

## The update rule (same discipline as gogaga-scoreboard, applied to sequencing)
**Any commit that closes a roadmap step, resolves a blocker ID referenced in it, or
changes what a phase gates on, must update `GO_LIVE_ROADMAP.md` in the same commit.**
Specifically:

- **A blocker resolves** → find every phase step referencing it, mark it done, check
  whether that phase is now fully cleared (all steps done) → if so, mark the phase
  cleared and **cascade**: check whether the next phase's gate condition is now
  met, and if the roadmap said "nothing in later phases is testable without this,"
  verify that claim and unlock/annotate the next phase accordingly.
- **A new blocker/decision surfaces** (found during any session) → insert it into
  the correct phase by **actual dependency** — does it block Phase 0's environment,
  is it independent code-fixable like Phase 9, or is it non-urgent debt like Phase
  10? Do not default-dump new items into Phase 9/10 without genuinely checking
  dependency order first; a miscategorized item breaks the "work top to bottom"
  promise this file makes to the reader.
- **An `GOGAGA_ANALYSIS_REPORT.md` score moves** → check if the roadmap references
  that area's completeness anywhere (a phase gate stating "X% required before Y")
  and update the reference, not just note it happened elsewhere.
- **Phase 9 (zero-credential code fixes) items get closed** → move them out of the
  active list into a "closed this phase" log at the bottom, don't just delete them
  — the history of what got fixed and when is itself useful.
- **Phase 10 (non-blocking debt)** — update if reprioritized (something moves from
  debt to urgent because a dependency changed) or if new debt is identified; this
  list should never be treated as append-only-forever without periodic review.

## Sequencing discipline (what makes this file worth having)
- Every phase 1–10 entry must answer three things, always: **(1)** exact steps to
  close it, **(2)** what closing it unlocks (name the phase/capability, not just
  "progress"), **(3)** who acts (Gowtham / Claude Code / external vendor/reviewer).
- Preserve the structural distinction exactly: **Phase 0** = environment-unblocking,
  must-go-first; **Phase 1–8** = credential/decision-gated, code mostly done
  already; **Phase 9** = zero-credential code work, doable anytime by anyone;
  **Phase 10** = tracked non-urgent debt. A new item goes into whichever bucket its
  REAL dependency profile matches, never wherever is convenient.
- Never let this file's phase count/ordering silently drift from what
  `BLOCKERS.md` and `GOGAGA_ANALYSIS_REPORT.md` actually contain — if the sets of
  referenced IDs diverge, that's a bug in this file, fix it as part of the same
  commit that caused the drift.
- Cross-reference by ID/name only — this file's job is sequencing, not detail
  duplication. If you find yourself copying a full blocker description in here
  instead of referencing an ID, that's the wrong move.
- **List blocker IDs individually, never as a range or slash-join** (`B-P2-01…06`,
  `B-FE1-02/03`) — the orphan checker (below) parses this file literally, and a
  shorthand hides IDs from it. This was a real bug found and fixed on install:
  compact ranges in the reference index hid 12 active blockers from their phases.

## Mechanical safety nets
- `scripts/check_roadmap_updated.sh` — the sibling of
  `scripts/check_scoreboard_updated.sh`. Fails a commit that touches `BLOCKERS.md`
  or mentions a blocker ID in its message without also touching
  `GO_LIVE_ROADMAP.md`, unless the message declares `no roadmap impact`. Runs as a
  CI job and on demand: `scripts/check_roadmap_updated.sh [<commit>]`.
- `scripts/check_roadmap_orphans.py` — the Task-4-shaped structural check.
  Computes each blocker ID's **last** status in `BLOCKERS.md` (the ledger appends
  resolution rows rather than mutating originals — grep any ID and you may find it
  twice), and reports two failure modes: an active (non-RESOLVED) blocker with no
  phase in the roadmap, or a roadmap reference with no ledger row at all. Run it:
  `python3 scripts/check_roadmap_orphans.py`. Resolved IDs are correctly allowed to
  be absent from the roadmap — completed work doesn't need a "what to do next"
  entry.

## Session-end checklist (run before your final commit of any session)
- [ ] Did this session close any roadmap step / resolve any referenced blocker ID? → roadmap updated, cascade-checked into the next phase?
- [ ] New blocker/decision found this session? → correctly placed by real dependency, not defaulted to the bottom?
- [ ] Does Phase 0 still accurately describe what MUST happen before anything else is testable?
- [ ] Do the roadmap's referenced IDs and area names still exist and match `BLOCKERS.md` / `GOGAGA_ANALYSIS_REPORT.md` exactly (no orphaned references — run `check_roadmap_orphans.py`)?
