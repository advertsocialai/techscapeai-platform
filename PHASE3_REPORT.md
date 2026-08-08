# GoGaga Backend — Phase 3 Report (Intelligence Layer)

Autonomous verification loop, 2026-08-08. Branch `claude/git-pull-hw7v9o`
(cut from `Klara-ai` @ `fa5dc9b`).

**This phase was a verification-and-repair loop, not a greenfield build.** The
Phase 3 feature code had already been committed — unreported and unreviewed —
in the squashed commit `d29254a "update"`. No `PHASE3_REPORT.md` existed, so
nothing had ever been checked against the T1–T10 spec. This loop audited all
ten tasks against that spec, found the gap between what was named and what was
actually wired, and fixed the defects that were fixable without credentials.

The headline: **most of Phase 3 is scaffolding that is not connected to
anything.** Nine of ten tasks have real files and real endpoints; the recurring
failure is a function that exists, is correct, and is never called.

---

## §Gate (Section A)

| Step | Finding |
|---|---|
| A1 — `PHASE2B_REPORT.md` §Timings | **File does not exist.** Phase 2B never ran. |
| A2 — `headroom_ms = 1100 − median_total_ms` | **Not computable.** No median, no p95, no per-stage breakdown exists — there has never been a voice turn to measure. |
| A3 — Decision rule | Third branch taken: *"Phase 2B not run / T6 still BLOCKED → build T3/T4 in MOCK/OFFLINE mode only."* |
| A4 — `BLOCKERS.md` | Zero rows RESOLVED since Phase 2. All five Phase 2 credential blockers still OPEN; `.env` does not exist in this sandbox at all. |
| A5 — Ground truth | Confirmed present: `travel_calls`, `travel_transcripts`(384-dim), `travel_leads`, `travel_packages`, `ai_engine.py`, `call_feed.py`, `/api/travel/v1/` prefix. Drift noted: the spec calls the table `ai_config`; it is really **`travel_ai_config`**. |

**Chosen T3/T4 pattern: MOCK/OFFLINE.** `LATENCY_INSUFFICIENT_FOR_INLINE` was
already logged as `DEBT-01`; it stands unchanged. Not re-litigated mid-loop.

One honest qualification the decision rule did not anticipate: T3/T4 are off
the voice-critical path, but **vacuously so — there is no voice turn loop to be
on.** `ai_engine.run_turn()` has zero call sites anywhere in `api/`. The webhook
accumulates every media frame and does one batch STT on `stop`. The AI never
speaks. So "per-turn suggestions for the monitoring human" are in practice
computed **once per call, after hangup**, when no supervisor can act on them.

---

## §Tasks

### T1 — Human takeover · 🟡 partially done
Built: 4 endpoints (`/calls/{id}/takeover/{monitor,barge,full,release}`), all
mounted and verified live. State machine `ai→monitoring→coaching→human`
(`takeover_service.py:34-39`) matches the migration CHECK and the WS enum. Every
transition writes a `travel_call_events` row (`_log_event`, called at 4 sites).

Not built, despite the names: **`full_takeover` never mutes the AI and `release`
never un-mutes it.** `_plivo_mute_participant` / `_plivo_unmute_participant`
(`takeover_service.py:116-132`) are defined and have **zero call sites** — both
paths only `logger.info("would mute...")`. Nothing anywhere reads `takeover_state`
to change AI behaviour, so "AI becomes a silent background note-taker" does not
exist. This is beyond the credential blocker: even with Plivo keys, nothing calls
them, and there is no `ai_member_id` column to identify the AI participant.

🔒 **Security fix applied this loop.** `GET /calls/{id}/events` called
`get_call_scoped(...)` and **discarded the result**. That function *returns
`None`* on an out-of-scope call — it does not raise, contrary to the comment
that sat next to it. Any agent-tier user could read any call's event log, and
because `get_events()` filters on `call_id` alone with no `business_id`, a
guessed UUID returned **another tenant's** events, including supervisor phone
numbers. Fixed in `takeover.py:146-158`; the result is now checked and 404s.

### T2 — AI Playbook / `travel_ai_config` · 🟡 partially done
Built: migration `0006` with all five jsonb columns, `GET/PUT /ai-config`,
`POST /ai-config/seed`, all mounted and verified live.

The central spec claim — *"escalation eval now reads `ai_config.escalation_rules`
instead of the hardcoded ₹1L constant"* — **is not met in either direction.**
There is no escalation evaluation anywhere: nothing compares `budget_inr`
against `budget_threshold`, and `intent_level` is read by zero lines of code.
The threshold is only string-interpolated into a prompt. And there was no Phase 2
constant to replace — `git log -S "100000"` shows ₹1,00,000 first appears in the
Phase 3 commit itself. The "default seed matches Phase 2 behaviour exactly
(regression-safe)" acceptance criterion is therefore **false**: Phase 3 invented
the rule and appended new text to the persona prompt.

Open defects (logged, not fixed — they need product decisions):
- Branch-scoped `PUT` patches the **business-wide** row when no branch row
  exists, so one branch manager silently rewrites every other branch's playbook.
- `UNIQUE (business_id, branch_id)` does not constrain business-wide rows —
  Postgres treats NULLs as distinct, so concurrent first-access can insert
  duplicate configs. Needs a partial unique index.
- `GET` is `require_role("viewer")` but performs an INSERT via auto-seed, so a
  read-only viewer can create rows.

### T3 — Live suggestions · 🟡 stubbed-verified
Keyword stub works with no API key and is genuinely fire-and-forget. But the
**WS contract does not match**: the spec assumed an existing `suggestion` type
in Phase 2's ws_contract — no such type was ever defined. The contract's Phase 3
type is `whisper` with fields `{suggestion, confidence, seq}`; the code emits
`{type:"suggestion", text, mode}`. Zero field overlap beyond `call_id`. A
dashboard written against the documented contract will not render these.

### T4 — Live sentiment · 🟡 stubbed-verified
Returns the three required dimensions; stub path safe with no key. Defects:
the module docstring claims "Claude enhancement available when
ANTHROPIC_API_KEY is set" — **there is no Claude path at all**, it is keyword-only.
Missing the contract's `urgency` dimension and `seq`. And
`travel_calls.sentiment_score` is not a running average of sentiment: it is an
EMA of **the intent dimension only**, seeded at 0.5, so the value is
arithmetically clamped to **[0.35, 0.65]** and can never express a strongly
positive or negative call.

### T5 — Post-call intelligence · 🟡 partially done — **2 idempotency bugs fixed**
The Sonnet pipeline, summary prompt, and write path are real. The acceptance
criterion was idempotency, and it did **not** hold. The guard is a truthiness
check on `summary`; two reachable paths produced a falsy summary and defeated it
permanently, after which every re-run re-patched `travel_leads` and appended
another `post_call_complete` event (migration `0005` has no unique constraint).

Both fixed and covered by new tests:
1. **Operator-precedence bug.** Implicit string concatenation binds tighter than
   `if/else`, so the false-branch was a bare `all_text` — `''` for a transcript
   with no customer text. Proven before the fix:
   `_stub_summary([]) -> ''`, `_stub_summary([{'text_original':'hi'}]) -> 'hi'`
   (prefix silently lost). Now always prefixed.
2. **`None / 100.0` TypeError.** `result.get("lead_score", 40)` does not apply
   the default when the key is present-and-null, which Claude's JSON can return.
   It raised *after* `travel_leads` was patched and *before* the summary landed —
   mutating the lead and leaving no guard. Now coerced with `or 40`. Also
   corrected `round(..., 4)` → `round(..., 3)` to match the `NUMERIC(4,3)` column
   instead of letting Postgres silently re-round.

Still missing: **extraction reconciliation.** The spec asked for conflict
resolution across per-turn extractions; the code is a blind last-writer-wins
overwrite that never reads the existing lead row. There is nothing to reconcile
against anyway, because the live extraction pass never runs (`run_turn` is dead).

### T6 — Transcript embeddings · 🟡 partially done — **event-loop stall fixed**
The single-embedder rule is **honored** — exactly one model instantiation
exists repo-wide, `BAAI/bge-small-en-v1.5` at `embeddings.py:26`, shared with the
Phase 2 wiki search. Dimensions match: column `vector(384)` = RPC param
`vector(384)`.

⚡ **Fixed this loop:** `embed_transcript()` was called **synchronously** inside
the async media-stream handler, despite a comment reading "fire-and-forget". It
is a plain `def` running ONNX inference plus a blocking Supabase write — and on
first call, a ~67MB model download — directly on the event loop, stalling every
other concurrent call's WebSocket. Added `schedule_transcript_embedding()`,
which offloads via `run_in_executor`, and switched the call site.

Not built: `match_travel_transcripts()` is **dead code with zero Python callers**;
semantic lead search does not exist (`list_leads` has no query parameter); there
is no sentiment analytics aggregate endpoint; no transcript backfill.

### T7 — Multi-business phone routing · 🟡 partially done — debt NOT killed
Migration `0007` is solid (unique phone number, FK, RLS + REVOKE, rollback), and
`_resolve_business_id(db, to_number)` correctly reads Plivo's `To` field.

But the acceptance criterion was killing the `PLIVO_BUSINESS_ID` single-tenant
debt, and **it is still a live fallback** at `webhooks_voice.py:66-67`. Combined
with the missing backfill — `0007` contains no `INSERT`, so the table ships
empty — **every call takes the legacy branch.** Behaviour is identical to
Phase 2. `DEBT` row stays OPEN; it cannot be flipped to RESOLVED.

Verified good: an unknown dialed number returns `None` and is handled, not a
500. It does fail *open* though — an unrecognized DID is answered with no tenant
context and no `travel_calls` row.

### T8 — Redis infra · 🟡 partially done — **silent-feed bug fixed**
JTI blacklist is correctly Redis-backed with a genuine graceful fallback
(short-circuits on empty `REDIS_URL` *before* `import redis`, so a missing
package cannot crash it — traced and confirmed for both call sites).

🐛 **Fixed this loop:** the call_feed Redis half was broken. `publish()` returns
immediately after `r.publish(...)` when Redis is active, delegating relay to
`subscribe_call()` — which had **zero callers**. The WS endpoint still used the
old in-process `register()` loop. The moment Redis was provisioned, every
`transcript` / `sentiment` / `takeover_state` / `call_status` frame would be
published to a channel with no subscriber and the live dashboard would go
**permanently silent with no error**. Wired `subscribe_call()` into
`calls.py`; it selects the backend internally and falls back to the in-process
path unchanged.

Also fixed: **`redis` was never declared in either requirements file** despite
two modules importing it — so the Redis path could never have engaged even if
`REDIS_URL` were set. Added `redis==5.2.1` to both.

### T9 — Telugu end-to-end + recording · 🔴 built-but-blocked → **effectively not built**
This is the honest finding of the loop. Phase 3's total contribution to T9 is
**seven log-only lines plus one docstring line**. `voice.py` — the engine-routing
layer T9 was meant to extend — **was not in the Phase 3 commit at all**; its last
change was Phase 2's `4023360`.

| Piece | State |
|---|---|
| Saarika STT (Telugu) | Real client exists — from **Phase 2**, not this phase |
| Bulbul TTS (Telugu) | **Missing.** No `bulbul` string anywhere in `api/`. TTS is ElevenLabs-only, hardcoded, no engine selector |
| Telugu STT routing | Function exists but is **unreachable**: `select_stt_engine()` keys off `travel_calls.language`, and **nothing ever writes that column** — it always defaults to `'en'` |
| Client-side barge-in | **Missing.** A comment describes it; no turn loop exists to interrupt |
| Per-participant recording | **Missing.** A log-only placeholder; no Plivo API call, no `<Record>`, no MPC XML |
| `recording_url` / Supabase storage | **Missing.** Column exists, no code writes it |

Critically, **most of this is not credential-blocked.** A Bulbul client, a
`select_tts_engine()`, writing `travel_calls.language`, and the recording HTTP
request are all writable and stub-testable today — exactly as the Sarvam STT
client already was in Phase 2. They were simply not written. Only the *live*
Telugu call and the *real* recording fetch need keys (B-P3-05/B-P3-06).

### T10 — Access matrix + hygiene · 🟡 partially done
Fixed this loop: **added all 5 missing takeover endpoints** to `matrix-spec.json`
(18 endpoints now, valid JSON). The prior waiver claimed they were not statically
expressible; that over-claimed. Two outcomes *are* static and are now asserted
using the all-zeros UUID — viewer→**403** (rejected at `require_role` before any
lookup) and agent+→**404** (clean scope-check miss, not a 500). These double as
the regression test for the T1 security fix. State-dependent outcomes (200/409,
assigned-vs-unassigned) still need live fixtures and are explicitly not asserted.

Also corrected a **false claim in two places**: `BLOCKERS.md` credited
`access_matrix.py`'s `mint()` fix to "P3 T10", and `matrix-spec.json`'s header
still described the bug as live. `git log --follow` shows the fix landed in
`acdf499` on **2026-08-03 — Phase 1**. P3 T10 never touched the file. The
attribution has been corrected rather than left as retroactive credit.

Not fixed: root `.env.example` is still missing 14 Settings fields including
Phase 3's own `REDIS_URL`. Edits to it are blocked by a permission deny rule on
`.env*` in this environment — logged as `B-P3-08`, needs a human. `api/.env.example`
is fully in sync (42/42 fields verified programmatically).

---

## §Evidence (real command output)

```
$ find app -name "*.py" -exec python -m py_compile {} \;
(exit 0, zero output — every file compiles)

$ python -c "import app.main; print(len(app.main.app.routes))"
IMPORT OK: 162 routes

$ pytest tests/ -q
23 passed, 2 warnings in 2.32s        # was 17 before this loop; +6 new
```

Phase 3 endpoints are really mounted:
```
/api/travel/v1/ai-config                                GET
/api/travel/v1/ai-config                                PUT
/api/travel/v1/ai-config/seed                           POST
/api/travel/v1/calls/{call_id}/events                   GET
/api/travel/v1/calls/{call_id}/takeover/barge           POST
/api/travel/v1/calls/{call_id}/takeover/full            POST
/api/travel/v1/calls/{call_id}/takeover/monitor         POST
/api/travel/v1/calls/{call_id}/takeover/release         POST
/ws/calls/{call_id}                                     WS
```

Failure-path evidence — live server, fixture settings (auth runs before any DB call):
```
POST   /calls/test-id/takeover/monitor   no token    -> 401
POST   /calls/test-id/takeover/barge     no token    -> 401
POST   /calls/test-id/takeover/full      no token    -> 401
POST   /calls/test-id/takeover/release   no token    -> 401
GET    /ai-config                        no token    -> 401
PUT    /ai-config                        no token    -> 401
POST   /calls/test-id/takeover/monitor   bad token   -> 401
GET    /ai-config                        bad token   -> 401
POST   /webhook/bogusprovider/voice                  -> 404
$ curl .../ai-config -H "Authorization: Bearer not.a.real.jwt"
{"detail":"Invalid token"}
```

Idempotency defects, reproduced before fixing:
```
_stub_summary([])                          -> ''          # falsy → guard defeated
_stub_summary([{'text_original':'hi'}])    -> 'hi'         # prefix silently lost
{'lead_score': None}.get('lead_score', 40) / 100.0
  -> TypeError: unsupported operand type(s) for /: 'NoneType' and 'float'
```

Dependency bug, reproduced and fixed:
```
$ pip install --dry-run -r requirements.txt      # BEFORE
ERROR: Cannot install httpx==0.28.1 and supabase==2.10.0 because these
package versions have conflicting dependencies.
ERROR: ResolutionImpossible

$ pip install --dry-run -r requirements.txt      # AFTER
DRYRUN_EXIT=0
```

---

## §Blocked

| B-ID | What is blocked | Unblock condition |
|---|---|---|
| B-P2-01/02 | T1 live audio (monitor/barge/full/release heard on a real call) | Plivo creds + `PUBLIC_BASE_URL` |
| B-P2-03 | T9 real Telugu STT accuracy | `SARVAM_API_KEY` |
| B-P2-04 | T3 Claude suggestions, T5 real Sonnet summaries | `ANTHROPIC_API_KEY` |
| B-P2-05 | T9 TTS / barge-in | `ELEVENLABS_API_KEY` |
| B-P2B-01 | Everything downstream of a real turn loop — T3/T4 as *live* features, T9 end-to-end | Run Phase 2B |
| B-P3-04 | T8 multi-worker proof (2-uvicorn test) | Provision Redis + set `REDIS_URL` |
| B-P3-06 | T9 recording URL | Plivo creds |
| B-SPRINT2B-01 | Every live DB check: `regression_check.sh`, `access_matrix.py`, all RLS proofs | Supabase access |
| B-SPRINT2B-02 | Real embedding vectors (T6 semantic quality) | Allowlist `huggingface.co` or pre-bake the ONNX weights |
| **B-P3-08** *(new)* | Root `.env.example` — 14 fields missing incl. `REDIS_URL` | Permission deny rule on `.env*` blocks edits; needs a human |

**No task was skipped for lack of a credential.** Every blocker above is an
external dependency. The genuinely damning findings — T9's absent Bulbul/routing/
recording code, T2's absent escalation eval, T6's dead RPC, T7's missing backfill —
are **not** credential-blocked and could have been built.

---

## §Decisions

1. **MOCK/OFFLINE for T3/T4** — forced by A3's third branch (no Phase 2B evidence).
   Not re-litigated.
2. **Verify-and-repair over rebuild.** Phase 3's code already existed unreported.
   Rewriting it would have destroyed working scaffolding and hidden what was
   actually wrong. The loop audited against spec and fixed defects in place.
3. **Fixed only what needed no product decision.** Security bypass, silent-feed
   bug, event-loop stall, idempotency, dependency resolution — all unambiguous.
   Left open, with reasons: T2's branch-PUT semantics (needs a call on whether a
   branch edit should fork a row), the WS contract mismatch (needs a call on
   whether code or contract is authoritative), T4's sentiment formula (needs a
   product definition of what the score means).
4. **Corrected false attribution rather than inheriting it.** `DEBT-03`'s
   "RESOLVED in P3 T10" was verifiably wrong. Retroactive credit in a ledger is
   worse than an open row, because it stops anyone from looking.
5. **Matrix rows use a nonexistent UUID deliberately** — asserts the two static
   outcomes without needing a live call, and pins the security fix.
6. **Root `requirements.txt` mirrors `api/`** rather than being deleted. It could
   not install at all; a root-context build (Railway auto-detect) was broken.

---

## §Debt

| ID | Debt |
|---|---|
| DEBT-01 | `LATENCY_INSUFFICIENT_FOR_INLINE` — unchanged; T3/T4 stay offline until 2B yields a headroom number |
| DEBT-04 *(new)* | **`ai_engine.run_turn()` is dead code.** No turn loop exists; the AI never speaks. T2/T3/T4 are all built against a loop that isn't there |
| DEBT-05 *(new)* | **WS contract drift.** `suggestion` vs contract's `whisper`; `sentiment` missing `seq` + `urgency`; `seq` is hardcoded `1` everywhere |
| DEBT-06 *(new)* | **Fire-and-forget tasks are unreferenced.** All three `schedule()` helpers discard the `ensure_future` handle; CPython may GC them mid-execution, and exceptions surface only as "Task exception was never retrieved" |
| DEBT-07 *(new)* | **`sentiment_score` is misnamed** — an EMA of intent alone, clamped to [0.35, 0.65] |
| DEBT-08 *(new)* | **`WebSocketDisconnect` path discards all buffered audio** — no transcript, no STT, no pipeline on an abrupt hangup |
| DEBT-09 *(new)* | Keyword-scorer substring false positives: `"may"` matches *maybe*; `"k "` matches any word ending in k, so a pure buying-intent line scores price-sensitive |

---

## §TODOs (owned, carried forward)

- **Build the turn loop** (Phase 2B). Everything in Phase 3 is downstream of it.
- Wire T9 properly: Bulbul TTS client, `select_tts_engine()`, **write
  `travel_calls.language`** (one line, unblocks all Telugu routing), Plivo
  recording request. None of this needs credentials to write.
- Kill `PLIVO_BUSINESS_ID`: backfill `business_phone_numbers`, drop the fallback.
- Give `match_travel_transcripts()` a caller: semantic lead search + backfill.
- Add the escalation **evaluation** T2 claims to have made configurable.
- Fix T2's branch-PUT fork + partial unique index on `(business_id) WHERE branch_id IS NULL`.
- Reconcile the WS contract (DEBT-05) — pick an authority, then align.
- Root `.env.example` (B-P3-08) — human needed.
- `0008` lacks `REVOKE EXECUTE ... FROM anon, authenticated` (inherited from `0004`).

## §Phase4Inputs

- **`travel_packages` exists and is seeded** — Phase 4 T1 must verify-don't-rebuild.
- **`payment_links` does not exist.** Clean build.
- **No scheduler exists in-app.** Phase 4 T5 introduces the first one; note
  `playbook_scheduler.py` already exists and should be extended, not duplicated.
- **Phase 4 T4 reports lean on Phase 3 T5 summaries** — these are real but stub-
  quality without `ANTHROPIC_API_KEY`, and every stub call writes
  `lead_score = 40` / `sentiment_score = 0.4`. **Reports built on this data will
  show a flat constant, not signal.** Degrade to raw aggregates per A1.
- **Phase 4 T7's activity_log retrofit should cover the takeover endpoints** —
  they currently write `travel_call_events` but no audit row.
- **`redis` is now declared** but no Redis is provisioned; anything Phase 4 builds
  on pub/sub inherits `B-P3-04`.
- Multi-currency (T8): `branches.currency` exists from Phase 1; no FX snapshot
  table exists yet.

---

## Files changed this loop

| File | Change |
|---|---|
| `api/app/routers/travel/takeover.py` | 🔒 Fixed RBAC bypass on `GET /calls/{id}/events` |
| `api/app/routers/travel/calls.py` | Wired `subscribe_call()` so the live feed survives Redis |
| `api/app/services/travel/embeddings.py` | Added `schedule_transcript_embedding()` (off event loop) |
| `api/app/routers/travel/webhooks_voice.py` | Call site switched to the non-blocking scheduler |
| `api/app/services/travel/post_call_service.py` | Fixed 2 idempotency-defeating bugs + NUMERIC rounding |
| `api/tests/test_post_call_stub.py` | **New** — 6 regression tests |
| `requirements.txt` | Fixed unresolvable pin; synced to `api/`; +`redis` |
| `api/requirements.txt` | +`redis==5.2.1` |
| `.claude/skills/.../matrix-spec.json` | +5 takeover endpoints; corrected stale claim |
| `BLOCKERS.md` | +B-P3-08, +DEBT-04..09; corrected DEBT-03 attribution |

---

=== PHASE 3 COMPLETE ===

**Status: T1 🟡 · T2 🟡 · T3 🟡 · T4 🟡 · T5 🟡 · T6 🟡 · T7 🟡 · T8 🟡 · T9 🔴 · T10 🟡**

Nothing in Phase 3 is ✅. The scaffolding is broadly real and the endpoints
respond correctly; what is missing is the wiring between them, and the turn loop
they all assume. Seven defects were found and fixed this loop — one of them a
cross-tenant authorization bypass, two of them latent bugs that would have
surfaced only in production (silent dashboards the moment Redis was provisioned;
an event loop stalling under concurrent calls). The single most valuable next
action is not a Phase 3 fix at all: **run Phase 2B and build the turn loop.**
