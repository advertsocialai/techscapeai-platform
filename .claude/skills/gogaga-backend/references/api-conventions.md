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
Every frame is JSON with a `type` discriminator. Defined types:

```json
{ "type": "transcript", "call_id": "...", "seq": 12, "speaker": "customer|ai|agent",
  "text_original": "...", "text_translated": "...", "language": "te|en|hi",
  "timestamp_ms": 1234567, "is_final": true }

{ "type": "whisper", "call_id": "...", "seq": 13,
  "suggestion": "...", "confidence": 0.82 }        // Phase 3

{ "type": "call_status", "call_id": "...",
  "status": "active|completed|failed", "mode": "ai|agent|conference" }

{ "type": "sentiment", "call_id": "...", "seq": 14,
  "scores": { "excitement": 0.7, "intent": 0.8, "price_sensitivity": 0.4, "urgency": 0.6 } }   // Phase 3
```

Rules: `seq` is monotonically increasing per call (lets the frontend detect gaps after reconnect). Unknown `type` must be ignored by clients, never crash. Auth: JWT on connect (header or first message — match what Phase 2 implements, then record here). Server never sends secrets over WS.

## Latency instrumentation log line (Phase 2, one per turn)
```
VOICE_TURN call_id=<uuid> seq=<n> stt_ms=<int> llm_ttft_ms=<int> llm_total_ms=<int> tts_ttfb_ms=<int> total_ms=<int> engine=<sarvam|deepgram> lang=<te|en|hi>
```
Grep-able (`grep VOICE_TURN`), one line, no JSON — this exact format is what gogaga-verifier's Phase 2 checks look for.
