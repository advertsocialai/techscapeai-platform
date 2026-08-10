#!/usr/bin/env bash
# Scoreboard safety net (see .claude/skills/gogaga-scoreboard/SKILL.md).
#
# Rule: a commit that touches scoring-relevant paths must either touch
# GOGAGA_ANALYSIS_REPORT.md in the same commit, or carry the literal string
# "no scoreboard impact" in its commit message (the deliberate, auditable
# escape hatch for changes that genuinely move no score).
#
# Usage:
#   scripts/check_scoreboard_updated.sh                # check HEAD
#   scripts/check_scoreboard_updated.sh <commit>       # check one commit
#   scripts/check_scoreboard_updated.sh <base>..<head> # check every commit in range
#
# Exit 0 = rule satisfied for every checked commit; exit 1 otherwise.
# This repo has no hook framework (verified: only .git/hooks/*.sample), so this
# runs as a CI job and on demand — it is intentionally NOT wired as a local hook.
set -euo pipefail

REPORT='GOGAGA_ANALYSIS_REPORT.md'
# Scoring-relevant paths: backend app+tests, both frontends, migrations/schema,
# CI workflows, deployment config. Docs and skills are not scoring-relevant.
RELEVANT='^(api/|agency-dashboard/(src/|package\.json|vite\.config)|customer-app/(src/|package\.json|vite\.config)|supabase/migrations/|database/|\.github/workflows/|Dockerfile|vercel\.json)'

check_commit() {
  local commit="$1"
  local files msg relevant
  files=$(git diff-tree --no-commit-id --name-only -r "$commit")
  msg=$(git log -1 --format=%B "$commit")
  relevant=$(grep -E "$RELEVANT" <<<"$files" || true)

  if [[ -z "$relevant" ]]; then
    echo "✓ $(git rev-parse --short "$commit"): no scoring-relevant paths touched."
    return 0
  fi
  if grep -Fqx "$REPORT" <<<"$files"; then
    echo "✓ $(git rev-parse --short "$commit"): touches scoring-relevant paths AND $REPORT."
    return 0
  fi
  if grep -Fqi 'no scoreboard impact' <<<"$msg"; then
    echo "✓ $(git rev-parse --short "$commit"): scoring-relevant paths, deliberate 'no scoreboard impact' declared."
    return 0
  fi

  echo "✗ $(git rev-parse --short "$commit"): touches scoring-relevant paths but NOT $REPORT." >&2
  echo "  Touched:" >&2
  sed 's/^/    /' <<<"$relevant" >&2
  echo "  Scoreboard rule (gogaga-scoreboard skill): update $REPORT in the same" >&2
  echo "  commit, or state 'no scoreboard impact' in the commit message if the" >&2
  echo "  change genuinely moves no area's completeness." >&2
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
