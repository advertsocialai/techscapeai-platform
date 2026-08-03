# GoGaga Curl Cookbook — verification commands per endpoint

All commands assume: `API=$GOGAGA_API` (default http://localhost:8000), `TOKEN` from login or make_test_token.py. Mask tokens in reports (last 4 chars).

## Auth lifecycle (Phase 1)

```bash
# Login (capture both tokens)
curl -s -X POST $API/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"'$GOGAGA_TEST_EMAIL'","password":"'$GOGAGA_TEST_PASSWORD'"}'

# Refresh — success path
curl -s -X POST $API/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"'$REFRESH'"}'
# Failure path (MANDATORY): garbage token → 401 clean JSON
curl -s -w "\n%{http_code}\n" -X POST $API/api/v1/auth/refresh \
  -H "Content-Type: application/json" -d '{"refresh_token":"garbage"}'

# Logout, then prove the token is dead (the commonly skipped check)
curl -s -X POST $API/api/v1/auth/logout -H "Authorization: Bearer $TOKEN"
curl -s -w "\n%{http_code}\n" $API/api/v1/wiki -H "Authorization: Bearer $TOKEN"
# expect 401 now
```

## RBAC probes (Phase 1)

```bash
VIEWER=$(python3 scripts/make_test_token.py --role viewer)
ADMIN=$(python3 scripts/make_test_token.py --role admin --branch $BRANCH_ID)

# viewer can read, cannot write
curl -s -o /dev/null -w "%{http_code}\n" $API/api/v1/wiki -H "Authorization: Bearer $VIEWER"      # 200
curl -s -o /dev/null -w "%{http_code}\n" -X POST $API/api/v1/wiki \
  -H "Authorization: Bearer $VIEWER" -H "Content-Type: application/json" \
  -d '{"title":"x","content":"y"}'                                                                # 403

# branch scoping: admin fetching an out-of-branch user id → 404 (NOT 403)
curl -s -o /dev/null -w "%{http_code}\n" $API/api/v1/users/$OUT_OF_BRANCH_ID \
  -H "Authorization: Bearer $ADMIN"                                                               # 404
```

## Users write chain (Phase 1 — run as one sequence)

```bash
# create → list shows it → patch → verify → delete → verify inactive + token dead
NEW=$(curl -s -X POST $API/api/v1/users -H "Authorization: Bearer $ADMIN" \
  -H "Content-Type: application/json" \
  -d '{"email":"chain@test.local","full_name":"Chain Test","role":"agent","branch_id":"'$BRANCH_ID'"}')
NEW_ID=$(echo $NEW | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -s -X PATCH $API/api/v1/users/$NEW_ID -H "Authorization: Bearer $ADMIN" \
  -H "Content-Type: application/json" -d '{"full_name":"Chain Renamed"}'

# role elevation by admin must fail
curl -s -o /dev/null -w "%{http_code}\n" -X PATCH $API/api/v1/users/$NEW_ID \
  -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" \
  -d '{"role":"admin"}'                                                                           # 403

# delete needs super_admin; then confirm status in DB, not just the 200
SA=$(python3 scripts/make_test_token.py --role super_admin)
curl -s -X DELETE $API/api/v1/users/$NEW_ID -H "Authorization: Bearer $SA"
# → then query Supabase: status must be 'inactive'; a token minted for that user must now 403
```

## Response hygiene checks (every endpoint)

```bash
# No secret leakage: response must not contain hash/password fields
curl -s $API/api/v1/users -H "Authorization: Bearer $ADMIN" | grep -iE "hash|password" && echo "LEAK" || echo "clean"

# Errors are JSON, not stack traces
curl -s $API/api/v1/users -H "Authorization: Bearer invalid" | head -3   # JSON error body, no Traceback
```

## Phase 2 additions

```bash
# Plivo webhook signature rejection (unsigned request must be refused)
curl -s -o /dev/null -w "%{http_code}\n" -X POST $API/webhook/voice -d "CallUUID=fake"            # 403

# Live calls list
curl -s $API/api/v1/calls/live -H "Authorization: Bearer $ADMIN"

# WebSocket feed during a call
python3 scripts/ws_probe.py --call-id $CALL_ID --token $ADMIN --duration 60

# Per-hop latency evidence: grep the app log for the turn instrumentation
grep -E "stt_ms|llm_ttft_ms|tts_ttfb_ms" api.log | tail -20
```

## Phase 4 additions

```bash
# Razorpay webhook: invalid signature must be rejected
curl -s -o /dev/null -w "%{http_code}\n" -X POST $API/webhook/razorpay \
  -H "X-Razorpay-Signature: invalid" -d '{"event":"payment.captured"}'                            # 400/403

# Scheduler: backdate a follow_up in DB, run the job, confirm status flips to sent
# Time-window guard: attempt an out-of-window send (e.g., 23:00 IST) → must be blocked/queued
```
