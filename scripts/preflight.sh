#!/usr/bin/env bash
# preflight.sh — confirm the environment can produce a meaningful test result.
# Exits 1 if testing now would yield false passes.
set -uo pipefail
BASE="${E2E_BASE_URL:-http://localhost:3000}"
FAIL=0
red(){ printf '\033[0;31m%s\033[0m\n' "$1"; }
yel(){ printf '\033[0;33m%s\033[0m\n' "$1"; }
grn(){ printf '\033[0;32m%s\033[0m\n' "$1"; }

echo "Playwright preflight — $BASE"
echo "═══════════════════════════════════════"

# Node
if command -v node >/dev/null 2>&1; then
  v=$(node --version | tr -d 'v' | cut -d. -f1)
  [ "$v" -ge 18 ] && grn "✓ node $(node --version)" || { red "✗ node 18+ required (have $(node --version))"; FAIL=1; }
else red "✗ node not found"; FAIL=1; fi

# Playwright MCP
if claude mcp list 2>/dev/null | grep -qi playwright; then grn "✓ playwright MCP registered"
else yel "⚠ playwright not in 'claude mcp list' — run: claude mcp add --scope user playwright npx @playwright/mcp@latest"; fi

# App reachable
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$BASE" 2>/dev/null || echo 000)
if [ "$code" = "000" ]; then red "✗ app unreachable at $BASE — is the dev server running?"; FAIL=1
elif [ "$code" -ge 500 ]; then red "✗ app returned $code"; FAIL=1
else grn "✓ app responding ($code)"; fi

# API health
api=$(curl -s --max-time 5 "$BASE/api/travel/v1/health" 2>/dev/null || echo "")
[ -n "$api" ] && grn "✓ API reachable" || yel "⚠ /api/travel/v1/health returned nothing"

# Service-role key — the standing blocker (BLK-2)
if grep -qs "SUPABASE_SERVICE_ROLE_KEY" .env.local .env 2>/dev/null; then
  grn "✓ service-role key present"
else
  red "✗ BLOCKED: no SUPABASE_SERVICE_ROLE_KEY"
  red "  No data can travel Postgres-to-screen."
  red "  Every screen will render its empty state and every result will be a FALSE PASS."
  FAIL=1
fi

# Two test agencies
if grep -qs "E2E_ALPHA_EMAIL" .env.local .env 2>/dev/null && grep -qs "E2E_BETA_EMAIL" .env.local .env 2>/dev/null; then
  grn "✓ two test agency accounts configured"
else
  yel "⚠ E2E_ALPHA_EMAIL / E2E_BETA_EMAIL not both set — tenant isolation testing not possible"
fi

# Production guard
case "$BASE" in
  *localhost*|*127.0.0.1*|*staging*|*preview*) grn "✓ non-production target" ;;
  *) red "✗ REFUSING: '$BASE' does not look like a test environment"; FAIL=1 ;;
esac

echo "═══════════════════════════════════════"
[ "$FAIL" -eq 0 ] && { grn "Ready to test."; exit 0; } || { red "Not ready. Fix the above — testing now produces false results."; exit 1; }
