# GoGaga Backend — Phase 2 Report (Voice Core)

Semi-autonomous loop run, 2026-08-03. Branch `Klara-ai`, commits `6732683..5a2eab1`
(T1 was completed in a prior turn; this run covers T2-T9). Zero permission
stops on autonomous work; the one genuine 📞 gate (T2's real dial-in) was
never reachable because `PLIVO_PHONE_NUMBER`/`PUBLIC_BASE_URL` don't exist.

## Environment reality vs. the task brief

T0 recon (this run and the prior one) found **zero** of the claimed Phase 2
credentials actually present in `.env`:

| Requirement | Status |
|---|---|
| `PLIVO_AUTH_ID` / `PLIVO_AUTH_TOKEN` / `PLIVO_PHONE_NUMBER` | absent |
| `PUBLIC_BASE_URL` (ngrok) | absent, `ngrok` not installed |
| `SARVAM_API_KEY` / `DEEPGRAM_API_KEY` / `ELEVENLABS_API_KEY` / `ANTHROPIC_API_KEY` | absent |

This directly contradicted the task brief's "Keys present" claim. Per the
loop's own blocker-handling rule (missing dependency ≠ waiting for a phone
call), every task was still attempted and built to the fullest extent
possible, verified with real, honest evidence wherever a meaningful proxy
existed, and marked BLOCKED only for the specific piece that genuinely
needs live infrastructure.

## Completed tasks

### T1 — Migrations + assigned-only leads RBAC (prior turn, `6732683`)
`travel_calls`/`travel_transcripts` created (RLS+revoke), `travel_leads`
gains `phone`/`assigned_agent`/`language`/`embedding`. `leads.py` scoped:
agent-tier sees only `assigned_agent=self`, manager+ unscoped. Verified
with real per-agent fixtures (2 leads→agentA, 3→agentB) — exact counts,
cross-agent 404. Regression green.

### T2 — Plivo answer webhook (`7cbe0ef`) — BLOCKED (credentials only)
`POST /api/travel/v1/webhook/{provider}/voice`. Plivo-signature auth
(X-Plivo-Signature-V2 + nonce), same stub-mode convention as the existing
Twilio/Wapi verifiers. **Verified**: stub-mode accepts + returns valid
`<Stream>` XML; unknown provider → 404; the HMAC-SHA256 crypto itself
(valid/tampered/missing signature, missing nonce, wrong URL) all behave
correctly against a locally-computed test signature.
**BLOCKED**: cannot reach the actual "dial and confirm" checkpoint — no
`PLIVO_PHONE_NUMBER` exists to give you, and no `PUBLIC_BASE_URL` for
Plivo to reach.

### T3 — Media stream WS handler (`a8e513b`) — structurally DONE
`WS /webhook/{provider}/stream` — parses Plivo's start/media/stop frame
protocol, manages `travel_calls` row lifecycle. **Verified without a live
call**: a simulated WS client sending real Plivo-shaped JSON frames
against a test `travel_calls` row confirmed the full `active→completed`
lifecycle (3 media frames counted, `duration_sec` computed correctly) and
the abrupt-disconnect→`failed` path. **BLOCKED**: real audio content over
the stream — no live call exists to prove it end to end.

### T4 — STT routing (`3c6f8a9`) — structurally DONE, quality BLOCKED
`transcribe_utterance()`: Deepgram default, Sarvam for Telugu. Batches the
whole call's audio and transcribes once on "stop" (real per-utterance VAD
segmentation needs live audio to build/verify — not attempted blind).
**Verified**: simulated `en` and `te` calls both route to the correct
engine and produce a `travel_transcripts` row each. **BLOCKED**: real
transcription accuracy, in either language — no API keys to call the real
services with.

### T5 — AI engine (`e16bd17`) — DONE (autonomous)
New `services/travel/ai_engine.py`: real Anthropic tool-use protocol —
`extract_lead_details` (writes to `travel_leads`) and `get_packages` (real
`travel_packages` lookup via the existing `CatalogService`, so quotes are
grounded in real inventory). Stub mode reuses `lead_service.py`'s existing
`extract_signals()` heuristic instead of a real tool-calling decision, but
still executes `get_packages` for real.

**Standalone-verified on 3 sample transcripts** (isolated test business,
Goa destination+package+lead): extraction correctly merged across turns
without overwriting earlier fields (destination+budget from turn 1,
duration from turn 2 — confirmed via direct DB read), `get_packages`
found the real seeded package and quoted its actual price (₹25,000,
4-day), the no-signal transcript produced no tool calls. **Not verified**:
real Claude persona quality, correct tool CHOICE by the model, multi-turn
coherence — no `ANTHROPIC_API_KEY`.

### T6 — TTS + VOICE_TURN log (`b9b1784`) — BLOCKED (full loop)
`synthesize_speech()` (ElevenLabs streaming) and `log_voice_turn()` built.
**Verified**: the log line format matches `api-conventions.md` exactly
(grep-able `VOICE_TURN call_id=... seq=... stt_ms=... llm_ttft_ms=...
llm_total_ms=... tts_ttfb_ms=... total_ms=... engine=... lang=...`).
**BLOCKED, and not attempted blind**: the actual deliverable (full 2-way
conversation test, barge-in, latency evidence over ≥5 turns) has no
meaningful proxy without live audio — unlike T3/T4/T5, there's no
DB-observable stand-in for "does barge-in interrupt mid-sentence in real
time." **Latency numbers cannot be honestly reported** — reporting
fabricated median/p95 figures would violate the "reported honestly" rule
worse than reporting nothing.

### T7 — Live calls API (`c32b44b`) — DONE (turned out fully verifiable!)
`GET /calls/live`, `GET /calls/{id}/transcript` (assigned-only via
`lead_id` join, mirrors T1's leads pattern), `WS /ws/calls/{call_id}`
(mounted with no `/api` prefix — matches `ws_probe.py` and the
api-contract.md target exactly; JWT via `Authorization` header on the
handshake). New `call_feed.py`: in-process pub/sub bridging the webhook
handler (producer) to WS subscribers (consumer).

This was the one 📞-classified task with a real testable proxy: a live WS
listener genuinely received `call_status(active)`→`call_status(completed)`
→`transcript` **in real time** while a simulated Plivo stream ran
concurrently — exact contract shape from api-conventions.md. Cross-agent
REST (404) and WS (403 at handshake) access both correctly rejected.
Regression green.

### T8 — Wiki semantic search (`83f606b`) — DONE (fully real, no blockers)
Chose **BAAI/bge-small-en-v1.5 via fastembed** (ONNX, no torch, no API
key, 384 dims, ~67MB) since no cloud embedding provider is configured.
Migration `0004` resizes the pre-existing `vector(1536)` columns (lossless
— zero rows had a populated embedding anywhere) and adds a
`match_travel_wiki()` cosine-similarity RPC. `WikiService.search()` tries
semantic first, falls back to the original keyword scorer.

**Real embedder, really works, no stub needed.** Backfilled the 15
pre-existing real wiki rows. Semantic-vs-keyword comparison on real
content, paraphrased query "what if I want my money back after cancelling
my trip": semantic correctly ranks **Cancellation Policy** + **Refund
Process** #1/#2; keyword search returns **neither** (no stemming:
"cancelling" ≠ "Cancellation"). Reconfirmed end-to-end through the real
`POST /wiki/search` HTTP endpoint.

### T9 — Hardening + acceptance (`4023360`, `5a2eab1`) — DONE
- **Failure injection**: shared `_call_with_retry()` (STT/TTS calls) —
  verified via fake-provider injection: always-500 exhausts exactly 3
  attempts then returns `None` gracefully (no exception); a
  fails-twice-then-succeeds provider recovers on attempt 3.
- **Outbound-hours guard**: `is_within_outbound_hours()`, 09:00-21:00 IST.
  Verified against all 4 boundary cases (08:59/09:00/20:59/21:00 IST) +
  2 interior points, all correct. **Not wired to any endpoint** — Phase 2
  only builds inbound voice, there's no outbound feature yet to gate.
- **matrix-spec.json**: added `GET /calls/live`; leads' assigned-only note
  updated from "deferred" to "done"; documented why webhook routes aren't
  in the matrix (Plivo-signature auth, not JWT).
- **Final acceptance sweep**: 36/36 cells pass (9 endpoints × 4 roles,
  real fixtures — `access_matrix.py` itself is still unfixed per the
  Phase 1 TODO, not attempted here since it was out of this loop's scope).
  Full logout→reuse-fails chain confirmed for all 4 roles.
- **Cleanup**: only the persistent `regression-fixture` business remains
  in the DB; every other test business created during this run was
  cascade-deleted.

## Blocked Items

| Task | Reason | Error/evidence | What's needed to unblock |
|---|---|---|---|
| T2 | No real phone number to give the human | `.env` masked-check: `PLIVO_PHONE_NUMBER` absent | Real Plivo account + `PLIVO_AUTH_ID`/`TOKEN`/`PHONE_NUMBER`, plus `PUBLIC_BASE_URL` (ngrok) |
| T3 | (depends on T2) no live audio to stream | — | Same as T2 |
| T4 | No STT provider keys | `.env` masked-check: `DEEPGRAM_API_KEY`/`SARVAM_API_KEY` absent | Real keys for both engines |
| T5 (partial) | No LLM key for real persona verification | `.env` masked-check: `ANTHROPIC_API_KEY` absent | Real key — tool-EXECUTION is proven, tool-CHOICE/persona quality is not |
| T6 | No TTS key + no live call to test barge-in/latency | `.env` masked-check: `ELEVENLABS_API_KEY` absent | Real key + a genuine phone call once T2/T3 are unblocked |

No task hit the 3-attempt code-failure threshold — every blocker above is
a missing external dependency, not a bug. Nothing was reverted; every
BLOCKED task still has its buildable code committed and structurally
verified where a meaningful proxy existed.

## Decisions made autonomously

1. **Dedicated `PLIVO_BUSINESS_ID` setting** — Plivo webhooks carry no
   JWT/business context, and there's no phone-number-per-business
   registry. One global `PLIVO_PHONE_NUMBER` can only realistically serve
   one tenant right now, so that tenant is named explicitly in config
   rather than guessed at. Real multi-business phone routing is a Phase 3
   TODO.

2. **STT is batch, not streaming.** Deepgram/Sarvam's real-time streaming
   endpoints are what production latency targets need, but building
   streaming STT integration with zero ability to verify it against real
   audio would be pure speculation. The batch (whole-utterance) path is
   what's actually testable today.

3. **Local embedder (fastembed/bge-small) over any cloud provider** — no
   cloud embedding key exists in this repo at all (not even a concept in
   `config.py` before this phase), and installing a full
   sentence-transformers+torch stack for a 384-vs-1024-dim local model
   choice wasn't worth the extra footprint for this phase's needs.
   Resized the pre-existing `vector(1536)` columns to `vector(384)` —
   flagged explicitly as a non-additive change even though nothing was
   destroyed (zero rows had data).

4. **T6's latency claims are omitted, not fabricated.** The task asked for
   "VOICE_TURN latency evidence over ≥5 turns, median/p95 vs ≤1.1s target,
   reported honestly even if over target." Honestly reporting requires
   real numbers from a real call; inventing plausible-looking numbers
   would be worse than admitting the data doesn't exist yet.

5. **`access_matrix.py` fix from Phase 1 was not touched again** — it's
   still broken exactly as documented in `PHASE1_REPORT.md`'s TODOs; this
   phase's acceptance sweep used the same real-fixture method as Phase 1
   instead. Fixing the script itself remains a TODO, not silently done as
   a side effect of this phase.

## TODOs for Phase 3

- Real Plivo/ngrok/Sarvam/Deepgram/ElevenLabs/Anthropic credentials —
  unblocks T2, T3 (real audio), T4 (real accuracy, both languages), T5
  (real persona verification), T6 (the entire full-loop deliverable).
- Streaming STT (replace the batch prerecorded-API path) — needed for the
  ≤1.1s latency target; unverifiable without live audio either way.
- Real per-utterance VAD segmentation (currently: one transcript per
  whole call, on "stop").
- Multi-business phone routing (replace the single `PLIVO_BUSINESS_ID`
  setting with a real phone-number-to-business table).
- Redis-backed `call_feed` pub/sub (currently in-process/single-worker,
  same acknowledged limitation as the existing in-memory jti blacklist).
- `access_matrix.py`'s `mint()` fix (Phase 1 TODO, still open).
- `cleanup_test_artifacts.py`'s markers (Phase 1 TODO, still open).
- Outbound-hours guard (`compliance.py`) needs to actually be wired into
  whichever Phase 3 feature makes outbound calls/messages.
- Wiki embedder could be upgraded to a larger local model (bge-large,
  1024-dim) or a real cloud provider once one is chosen/funded — 384-dim
  bge-small was picked for footprint, not because it's the ceiling.

=== PHASE 2 COMPLETE ===

BLOCKED ITEMS: T2 (no real call reachable), T3 (depends on T2), T4
(real STT quality), T5 partial (real persona quality), T6 (full
2-way loop + latency evidence) — all credential/infrastructure gaps,
not code failures. T1, T7, T8, T9 fully done. T5 structurally done,
persona-quality unverified.
