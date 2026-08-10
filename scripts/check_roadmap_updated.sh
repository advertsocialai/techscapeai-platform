#!/usr/bin/env bash
# Roadmap safety net (see .claude/skills/gogaga-golive-roadmap/SKILL.md).
#
# Rule: a commit that touches BLOCKERS.md, or whose message references a
# blocker ID (BLK-*, B-<phase>-<n>, DEBT-*), must also touch
# GO_LIVE_ROADMAP.md in the same commit — or carry the literal string
# "no roadmap impact" in its commit message (the deliberate, auditable
# escape hatch for a ledger edit that changes no phase gate — e.g. fixing a
# typo in a row that was already correctly sequenced).
#
# This is the sibling of scripts/check_scoreboard_updated.sh: that one keeps
# GOGAGA_ANALYSIS_REPORT.md (the score) honest; this one keeps
# GO_LIVE_ROADMAP.md (the sequence) honest. Different trigger, same shape.
#
# Usage:
#   scripts/check_roadmap_updated.sh                # check HEAD
#   scripts/check_roadmap_updated.sh <commit>       # check one commit
#   scripts/check_roadmap_updated.sh <base>..<head> # check every commit in range
#
# Exit 0 = rule satisfied for every checked commit; exit 1 otherwise.
# Not wired as a local hook (this repo has none — only .git/hooks/*.sample):
# runs as a CI job and on demand, same as its scoreboard sibling.
set -euo pipefail

ROADMAP='GO_LIVE_ROADMAP.md'
LEDGER='BLOCKERS.md'
# A blocker-ID token: BLK-6, B-P2-01, B-FE7-08, B-SPRINT2B-01, DEBT-20, ...
ID_PATTERN='(BLK-[0-9]+|B-[A-Za-z0-9]+-[0-9]+|DEBT-[0-9]+)'

check_commit() {
  local commit="$1"
  local files msg relevant

  files=$(git diff-tree --no-commit-id --name-only -r "$commit")
  msg=$(git log -1 --format=%B "$commit")

  relevant=0
  grep -Fqx "$LEDGER" <<<"$files" && relevant=1
  grep -Eq "$ID_PATTERN" <<<"$msg" && relevant=1

  if [[ "$relevant" -eq 0 ]]; then
    echo "✓ $(git rev-parse --short "$commit"): no blocker-ID references touched."
    return 0
  fi
  if grep -Fqx "$ROADMAP" <<<"$files"; then
    echo "✓ $(git rev-parse --short "$commit"): references a blocker ID AND touches $ROADMAP."
    return 0
  fi
  if grep -Fqi 'no roadmap impact' <<<"$msg"; then
    echo "✓ $(git rev-parse --short "$commit"): blocker-ID reference, deliberate 'no roadmap impact' declared."
    return 0
  fi

  echo "✗ $(git rev-parse --short "$commit"): references a blocker ID but NOT $ROADMAP." >&2
  echo "  Roadmap rule (gogaga-golive-roadmap skill): when a commit resolves a" >&2
  echo "  BLK-*/B-*-*/DEBT-* item, closes a roadmap step, or changes what a" >&2
  echo "  phase gates on, update $ROADMAP in the same commit — mark the step" >&2
  echo "  done, cascade-check whether the phase is now cleared, and whether the" >&2
  echo "  next phase's gate is now met. State 'no roadmap impact' in the commit" >&2
  echo "  message only if the change genuinely moves no phase gate (e.g. a" >&2
  echo "  wording fix in an already-correctly-sequenced row)." >&2
  return 1
}

target="${1:-HEAD}"
fail=0
if [[ "$target" == *..* ]]; then
  while read -r c; do
    check_commit "$c" || fail=1
  done < <(git rev-list --reverse "$target")
else
  check_commit "$target" || fail=1
fi
exit "$fail"
