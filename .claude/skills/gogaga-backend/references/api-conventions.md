# GoGaga API Conventions — Response Shapes, Errors, WebSocket Contract, Pagination

The shapes every endpoint must follow. Recon rule: if existing auth.py/wiki.py responses differ from this, MATCH THE EXISTING CODE and update this file — consistency with live code beats this spec.

## Error envelope (all non-2xx)
```json
{ "detail": "Human-readable message" }
```
- FastAPI's HTTPException default — keep it. No stack traces, no internal paths, no SQL in messages.
- 401 = not authenticated (bad/expired/blacklisted token) · 403 = authenticated but not allowed (role/status) · 404 = not found OR out-of-branch (never reveal which) · 422 = validation (FastAPI default body is fine).

## Success responses
- Single resource: the object itself (Pydantic model), not wrapped.
- Lists: `{ "items": [...], "total": n }` — enables pagination without breaking clients later.
- Creates: return the created object incl. id; 200 or 201 — match whatever auth.py does today (confirm at recon), then be consistent everywhere.
- Deletes (soft): `{ "id": "...", "status": "inactive" }`.

## Pagination (any list that can grow: users, leads, calls, payment_links)
Query params: `limit` (default 50, max 200) + `offset` (default 0). Response carries `total`. Skip on small fixed lists (branches).

## Datetime + money
- All timestamps: ISO 8601 UTC in responses (`2026-08-01T12:00:00Z`); DB stores timestamptz.
- Money: numeric INR values as numbers (not strings), field names amount_* ; never floats in Python — use Decimal in services.

## WebSocket message contract — /ws/calls/{call_id}

> **CORRECTED 2026-08-08.** This section previously described a contract the
> code does not implement, and a frontend was built against it before the
> divergence was caught. What follows was read off the **five** actual
> `call_feed.publish(...)` call sites. Grep that symbol before trusting any doc,
> including this one.

Every frame is JSON with a `type` discriminator. **Exactly five types are
emitted:**

```json
{ "type": "transcript", "call_id": "...", "seq": 1, "speaker": "customer|ai|agent",
  "text_original": "...", "text_translated": null, "language": "te|en|hi",
  "timestamp_ms": 1234567, "is_final": true }

{ "type": "call_status", "call_id": "...",
  "status": "active|completed", "mode": "ai|agent" }

{ "type": "sentiment", "call_id": "...", "transcript_id": "...",
  "scores": { "excitement": 0.7, "intent": 0.8, "price_sensitivity": 0.4 } }

{ "type": "suggestion", "call_id": "...", "text": "...", "mode": "claude|keyword" }

{ "type": "takeover_state", "call_id": "...",
  "takeover_state": "ai|monitoring|coaching|human" }
```

### Do NOT build against these — no publisher exists

| Type | Status |
|---|---|
| `whisper` | **Never emitted.** The real frame is `suggestion`, with `{text, mode}` — zero field overlap with the old `{suggestion, confidence}`. No confidence is computed anywhere. |
| `speaking`, `intent`, `event`, `extraction` | **Never emitted.** They appear in FE loop prompts only. UI built on them renders permanently empty (`DEBT-15`). |
| `summary` | **Never emitted** on this feed. The only `"type": "summary"` in the repo is a follow-up-ladder step in `followup_service.py`. |
| `urgency` (4th sentiment dimension) | **Not computed.** `score_text()` returns exactly three. |
| `status: "failed"`, `mode: "conference"` | Not written by any code path. |

### Rules

- **`seq` is hardcoded to `1`** at its single emit site, and only `transcript`
  carries it. It is NOT monotonic. **Do not build gap detection on it** — it
  would fire constantly and lie to the user.
- Unknown `type` must be ignored by clients, never crash.
- **Auth: the `Sec-WebSocket-Protocol` subprotocol — `['bearer', <jwt>]`.**
  This replaced a header-only dependency that made the endpoint *unreachable
  from any browser*, since the `WebSocket` constructor cannot set headers. The
  server echoes `bearer` on accept; RFC 6455 says a browser silently drops a
  connection whose offered subprotocol was not echoed. `Authorization: Bearer`
  still works for non-browser clients; `?token=` is accepted last (it leaks the
  JWT into access logs).
- Server never sends secrets over WS.

## Latency instrumentation log line (Phase 2, one per turn)
```
VOICE_TURN call_id=<uuid> seq=<n> stt_ms=<int> llm_ttft_ms=<int> llm_total_ms=<int> tts_ttfb_ms=<int> total_ms=<int> engine=<sarvam|deepgram> lang=<te|en|hi>
```
Grep-able (`grep VOICE_TURN`), one line, no JSON — this exact format is what gogaga-verifier's Phase 2 checks look for.
