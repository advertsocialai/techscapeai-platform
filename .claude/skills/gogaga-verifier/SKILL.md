---
name: gogaga-verifier
description: Verification and testing toolkit for the GoGaga/TechScapeAI FastAPI backend. ALWAYS use this skill when verifying any backend task, running acceptance checks, testing endpoints, checking RBAC/permissions, minting test tokens, running the access matrix, doing the regression check, or writing PHASE reports. Trigger on any mention of "verify", "test the endpoint", "acceptance", "access matrix", "regression", "curl the API", or when completing any task in a phase agent loop. A task is NEVER done until this skill's verification patterns pass.
---

# GoGaga Verifier

Verification toolkit for the GoGaga backend. Core principle: **a task is done when its verification commands pass — including failure paths — not when code compiles.**

## The three verification layers (run in this order)

1. **Regression floor** (after EVERY task): `scripts/regression_check.sh` — login must return 200 + tokens, GET /wiki with that token must return 200. If this fails, fixing it preempts everything else.
2. **Task verification** (per task): the specific success + failure path checks for what was just built. Templates in `references/curl-cookbook.md`.
3. **Acceptance sweep** (end of phase): `scripts/access_matrix.py` — every endpoint × every role, expected vs actual status codes, printed as a table for the phase report.

## Setup (once per session)

Set environment for the scripts:
```bash
export GOGAGA_API=http://localhost:8000        # FastAPI base URL
export GOGAGA_TEST_EMAIL=regression-fixture@techscapeai.com   # persistent P1 dev fixture — do not delete
export GOGAGA_TEST_PASSWORD=<working password>
export GOGAGA_LOGIN_PATH=http://localhost:8000/api/techscape/v1/auth/login   # real prefix has /v1 — regression_check.sh's default lacks it
export GOGAGA_WIKI_PATH=http://localhost:8000/api/travel/v1/wiki             # same
# Only needed for token minting (read from api's own config if possible):
export GOGAGA_JWT_SECRET=<settings.JWT_SECRET value>   # access tokens; refresh uses JWT_REFRESH_SECRET
export GOGAGA_JWT_ALG=HS256
export GOGAGA_TEST_BIZ=<an ACTIVE ts_businesses.id>      # required: tokens carry a biz claim
export GOGAGA_TEST_SUB=<a real ts_users.id>              # recommended: require_business fetches the user row
# For access_matrix.py specifically — one real user PER ROLE is required
# (this repo's RBAC re-reads the DB row, not the token's role claim):
export GOGAGA_SUB_SUPER_ADMIN=<user id with role=super_admin>
export GOGAGA_SUB_ADMIN=<user id with role=manager>      # yes, manager — see core/deps.py mapping
export GOGAGA_SUB_AGENT=<user id with role=agent>
export GOGAGA_SUB_VIEWER=<user id with role=viewer>
```
IMPORTANT: read the JWT secret/alg/claim-shape from `api/app/core/security.py` first — the minting script now matches the real shape (sub/biz/role/type/jti, HS256, JWT_SECRET). require_business also validates the biz row is ACTIVE and fetches the user — use real ids. Real route prefixes are `/api/techscape/v1/*` and `/api/travel/v1/*` (P1 recon corrected this from an earlier no-`/v1` assumption).

## Scripts (run, don't rewrite)

- `scripts/regression_check.sh` — the floor check. Exit 0 = green.
- `scripts/make_test_token.py --role viewer --biz $GOGAGA_TEST_BIZ [--sub $GOGAGA_TEST_SUB] [--ttl 300]` — mint a short-lived token for any role. Used for RBAC testing without creating real users.
- `scripts/access_matrix.py --spec references/matrix-spec.json` — runs every endpoint × role combo, prints PASS/FAIL table, exits non-zero if any mismatch. Update matrix-spec.json as endpoints are added each phase.
- `scripts/ws_probe.py --call-id <id>` — connects to /ws/calls/{id}, prints messages for 30s. Phase 2+ WebSocket verification.
- `scripts/cleanup_test_artifacts.py [--yes]` — after acceptance sweeps: removes rows the matrix created (wiki 'matrix-test', users *@test.local, 'Matrix Test%' branches). Dry-run by default; only touches the hardcoded test markers.

## Verification rules

- **Failure paths are mandatory**: bad token → 401 clean JSON (never a stack trace); insufficient role → 403; out-of-branch → 404. A task claiming success without failure-path evidence is incomplete.
- **Evidence = real output**: paste actual curl/script output in reports, trimmed. Never "it should work."
- **DB state checks**: after writes, confirm in Supabase (e.g., soft-delete → status='inactive' in the users table, not just a 200 response).
- **Token invalidation chains**: after logout or user deactivation, prove the OLD token now fails (401/403) — this is the most commonly skipped check.
- **Secrets discipline**: mask all tokens/keys in output to last 4 chars.
- **3-attempt rule**: verification failing 3 times → STOP, report blocker, don't improvise.
- **Scoreboard discipline**: `GOGAGA_ANALYSIS_REPORT.md` at the repo root is the combined completeness scoreboard for both apps. Any task that moves an area — up or down, including newly discovered gaps — updates `GOGAGA_ANALYSIS_REPORT.md` **in the same commit** as the change. A verification pass that changes a number but leaves the scoreboard stale is incomplete.

## Per-phase verification focus

- **P1**: access matrix across 4 roles; refresh/logout token lifecycle; branch scoping (admin 404s on out-of-branch); soft-delete + token invalidation chain.
- **P2**: real-call checks (transcript rows match what was said; calls row lifecycle); `ws_probe.py` shows live feed; per-hop latency logged every turn (stt_ms, llm_ttft_ms, tts_ttfb_ms); Plivo signature rejection test (unsigned request → 403).
- **P2.5**: one flow touches all 4 new tables (lead → reassign → payment link → auto-seeded follow_ups); RLS verified per table.
- **P3**: sentiment jsonb populated per chunk; score recompute on call end; takeover keeps transcript flowing (ws_probe during a two-phone test); whisper messages appear on the same WS.
- **P4**: Razorpay webhook signature verify + lookup-confirm before status=paid; scheduler fires on backdated scheduled_at; 09:00–21:00 IST guard blocks out-of-window sends; dashboard/summary numbers reconcile against raw table counts.

## Phase report template

End every phase with `PHASE<N>_REPORT.md`: endpoints added · files touched · access matrix table (from access_matrix.py output) · failure-path evidence · TODOs left · deviations from plan discovered during recon.

For the full curl command cookbook per endpoint, read `references/curl-cookbook.md`.

## Dead-code sweep — run before calling any phase done

`scripts/find_dead_code.py` finds functions that are DEFINED, correct, and NEVER
CALLED. This is the most expensive recurring defect in this repo: it has landed
at least four times and passed review every time, because the code itself was
fine and only the wiring was missing. Tests cannot catch it — nothing fails, the
feature is simply absent.

```bash
python3 .claude/skills/gogaga-verifier/scripts/find_dead_code.py --min-lines 8
```

Confirmed catches: `ai_engine.run_turn()` (no voice turn loop, so the AI never
replies mid-call), `voice.synthesize_speech()` (TTS never plays),
`voice.log_voice_turn()` (the VOICE_TURN latency line the blueprint mandates is
never emitted), `call_feed.subscribe_call()` (the live dashboard would have gone
silent the moment Redis was provisioned).

Each hit is a QUESTION — "who should be calling this?" — not a verdict. Every
past instance here was a missing call, so the fix is almost always to WIRE IT
UP, never to delete.

---

## ⚠️ Fixture usability — learned the hard way, 2026-08-09

**The tenant-B fixture could not log in.** `0018` seeded four accounts at
`@regression-fixture-tenant-b.test`. `LoginIn.email` is a Pydantic `EmailStr`,
and email-validator rejects RFC 2606 special-use names:

```
422 -> "value is not a valid email address: The part after the @-sign is a
        special-use or reserved name that cannot be used with email"
```

Every access-matrix run against tenant B would have died at authentication,
before testing a single permission — and the failure would have looked like a
broken RBAC layer rather than a bad address. Fixed in `0020`; the fixture now
uses `@regression-fixture-tenant-b.example.com` (IANA-reserved for
documentation, so still undeliverable, but accepted by every validator).

**The rule this generalises to, and it applies to every fixture this skill
touches:**

> A row the database accepts can still be unusable by the application.
> A fixture is not ready when the INSERT succeeds — it is ready when you have
> **round-tripped it through the API**: minted a token for it, called one
> endpoint as it, and got a 2xx.

Do that once, before building a matrix on top of it. The alternative is an
access matrix that fails uniformly for a reason that has nothing to do with
access.

### Before running the access matrix, confirm the fixture actually authenticates

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  "$API/api/techscape/v1/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"owner@regression-fixture-tenant-b.example.com","password":"<pw>"}'
# 200 = usable · 422 = the ADDRESS is rejected, nothing to do with credentials
#                401 = address fine, password wrong
```

**422 and 401 mean completely different things here.** A 422 is the address
being refused by the validator; no password will ever fix it. Distinguishing
them is the difference between a five-minute fix and hours spent debugging RBAC
that was never broken.

### Not every `.test` address is a bug — check whether it is validated

`api/tests/test_ws_handshake_live.py` uses `agent@fixture.test` in `_USER_ROW`.
That is a **mocked DB row**, never passed through `EmailStr`, so it is fine and
must not be "fixed". Only addresses that cross a Pydantic request boundary are
affected. Chasing the rest is a false positive.
