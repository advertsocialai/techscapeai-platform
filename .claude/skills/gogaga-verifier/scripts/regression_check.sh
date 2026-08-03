#!/usr/bin/env bash
# GoGaga regression floor check — login + wiki must stay green.
# Usage: GOGAGA_API, GOGAGA_TEST_EMAIL, GOGAGA_TEST_PASSWORD must be set.
# Exit 0 = green. Any other exit = regression broken; fix before anything else.
set -euo pipefail

API="${GOGAGA_API:-http://localhost:8000}"
EMAIL="${GOGAGA_TEST_EMAIL:?Set GOGAGA_TEST_EMAIL}"
PASS="${GOGAGA_TEST_PASSWORD:?Set GOGAGA_TEST_PASSWORD}"

echo "== Regression check against $API =="
echo "(paths overridable: GOGAGA_LOGIN_PATH / GOGAGA_WIKI_PATH — confirm real prefixes at recon)"

# 1) Login
LOGIN_RES=$(curl -s -w "\n%{http_code}" -X POST "${GOGAGA_LOGIN_PATH:-$API/api/techscape/auth/login}" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
LOGIN_CODE=$(echo "$LOGIN_RES" | tail -1)
LOGIN_BODY=$(echo "$LOGIN_RES" | sed '$d')

if [ "$LOGIN_CODE" != "200" ]; then
  echo "FAIL: POST /auth/login returned $LOGIN_CODE"
  echo "$LOGIN_BODY" | head -5
  exit 1
fi

TOKEN=$(echo "$LOGIN_BODY" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('access_token') or d.get('data',{}).get('access_token',''))" 2>/dev/null || true)
if [ -z "$TOKEN" ]; then
  echo "FAIL: login 200 but no access_token found in body"
  exit 1
fi
echo "PASS: login 200, token ...${TOKEN: -4}"

# 2) Wiki read with the token
WIKI_CODE=$(curl -s -o /tmp/wiki_out.json -w "%{http_code}" "${GOGAGA_WIKI_PATH:-$API/api/travel/wiki}" \
  -H "Authorization: Bearer $TOKEN")
if [ "$WIKI_CODE" != "200" ]; then
  echo "FAIL: GET /wiki returned $WIKI_CODE"
  head -5 /tmp/wiki_out.json
  exit 1
fi
echo "PASS: GET /wiki 200"

echo "== REGRESSION GREEN =="
