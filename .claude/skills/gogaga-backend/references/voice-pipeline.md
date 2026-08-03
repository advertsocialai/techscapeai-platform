# GoGaga Voice Pipeline Reference (Phase 2 built — Phase 2B extends)

## India media anchoring rule (HARD)
**NEVER bridge a domestic +91 PSTN leg to an international relay.**
This violates TRAI interconnect rules and is a show-stopper for the Plivo account.
- Foreign supervisors: must join via browser/WebRTC or SIP **on an India Plivo account**,
  OR receive transcript-only access (no audio fork to international).
- Any code mixing a domestic India leg with an international PSTN leg is an immediate reject.
Label violations: "Violates Media Anchoring — REJECT".

---

## Current architecture (Phase 2 — bare Stream, batch STT)

```
Caller (+91) → Plivo India (140-series CLI, DLT-registered)
  → POST /api/travel/v1/webhook/plivo/voice   (Plivo signature verified)
      creates travel_calls row + travel_leads row (if new phone)
      returns <Stream bidirectional="true" keepCallAlive="true">wss://...plivo/stream</Stream>
  → WS /api/travel/v1/webhook/plivo/stream    (Plivo media frames)
      accumulates raw audio bytes per call
      on "stop" frame → STT batch transcription (whole utterance) → travel_transcripts row
      → call_feed.publish() → /ws/calls/{call_id} subscribers
  → GET /api/travel/v1/calls/live             (REST: active calls)
  → GET /api/travel/v1/calls/{id}/transcript  (REST: transcript rows)
  → WS  ws://<host>/ws/calls/{call_id}        (no /api prefix — call feed)
```

**What's NOT in this path yet (Phase 2B will add):**
- No real-time turn loop — STT fires once on "stop", AI engine is never called mid-call
- No streaming TTS → no audio played back to the caller
- No barge-in
- MPC (Multiparty Call) not used — bare `<Stream>` only

---

## File map (Phase 2 real locations)

| File | Role |
|---|---|
| `api/app/routers/travel/webhooks_voice.py` | Answer webhook (POST) + media stream WS handler |
| `api/app/routers/travel/calls.py` | Live calls REST + /ws/calls WS router |
| `api/app/services/travel/voice.py` | Plivo sig verification · XML builders · STT/TTS helpers · retry · VOICE_TURN log |
| `api/app/services/travel/ai_engine.py` | Claude tool-calling persona (extract_lead_details, get_packages) |
| `api/app/services/travel/call_feed.py` | In-process pub/sub (producer → consumers on /ws/calls) |
| `api/app/services/travel/compliance.py` | `is_within_outbound_hours()` — 09:00–21:00 IST; NOT wired to any endpoint yet |
| `api/app/services/travel/embeddings.py` | fastembed bge-small encoder (wiki semantic search) |
| `supabase/migrations/0003_*` | travel_calls + travel_transcripts DDL + travel_leads columns |
| `supabase/migrations/0004_*` | vector(384) resize + match_travel_wiki() RPC |

---

## Endpoint reference

### Plivo webhooks (NOT JWT — Plivo-signature auth)
```
POST /api/travel/v1/webhook/plivo/voice
  Headers: X-Plivo-Signature-V2, X-Plivo-Signature-V2-Nonce
  → travel_calls row created, returns XML <Stream>
  → BLOCKED in stub mode if PLIVO_BUSINESS_ID is empty (logs warning, still answers)

WS   /api/travel/v1/webhook/plivo/stream
  → Plivo media frames (start/media/stop events)
  → on stop: batch STT → travel_transcripts → call_feed.publish()
```

### Calls API (JWT via Authorization header — same get_current_user pattern)
```
GET  /api/travel/v1/calls/live
  → list active travel_calls; agent-tier sees only calls whose lead is assigned to them
GET  /api/travel/v1/calls/{id}/transcript
  → list travel_transcripts for a call (same assigned-only scoping)
WS   ws://<host>/ws/calls/{call_id}        ← NO /api prefix, mounted directly on app
  → push feed; agent-scoped access at handshake (WS Depends(get_current_user))
  → message types: call_status(active|completed) · transcript · takeover_state
```

---

## ai_engine.py — rules
- **Two tools only**: `extract_lead_details` (writes to travel_leads via LeadService) and `get_packages` (real DB lookup via CatalogService — quotes grounded in inventory, never hallucinated)
- Bounded tool-loop: max 4 iterations per turn (never infinite)
- Stub mode (no ANTHROPIC_API_KEY): falls back to `lead_service.extract_signals()` keyword heuristic + still runs get_packages for real
- System prompt enforces: short spoken sentences only, no lists/markdown, no filler words
- `settings.AI_MODEL` default: `claude-sonnet-4-6`
- Do NOT import or modify `services/techscape/ai_service.py` — that is the techscape-scoped service, out of scope

---

## VOICE_TURN log format (exact — grep-able)
```
VOICE_TURN call_id=<uuid> seq=<int> stt_ms=<int> llm_ttft_ms=<int> llm_total_ms=<int> tts_ttfb_ms=<int> total_ms=<int> engine=<deepgram|sarvam> lang=<en|hi|te>
```
Emitted by `voice.log_voice_turn()`. One line per completed turn. Latency target: total_ms ≤ 1100 (median), ≤ 1400 (p95).

---

## Retry + failure handling (Phase 2 T9)
`voice._call_with_retry(fn, attempts=3, backoff_sec=0.5)` wraps every external provider call:
- 5xx or network error → retry (max 3, with backoff 0.5s × attempt)
- 4xx → not retried (our bug, not provider transient)
- After all attempts exhausted → returns `None`; caller degrades gracefully (empty audio / stub transcript — never crashes the call)

---

## STT routing
`voice.select_stt_engine(language)`:
- language starts with "te" → `"sarvam"` (Saarika v2, Telugu/code-mix)
- everything else → `"deepgram"` (Nova-2, English/Hindi)

`voice.transcribe_utterance(engine, audio_bytes, language)`:
- Deepgram: POST `api.deepgram.com/v1/listen?language=en&model=nova-2` (WAV bytes)
- Sarvam: POST `api.sarvam.ai/speech-to-text` (multipart WAV, model=saarika:v2)
- Stub mode: returns `{"text": "[stub transcript ...]", "stub": True}` if key absent

---

## TTS (Phase 2 T6 skeleton — NOT exercised without a live call)
`voice.synthesize_speech(text, voice_id)`:
- ElevenLabs `eleven_turbo_v2_5` streaming endpoint
- Returns raw audio bytes (caller sentence-chunks the LLM output)
- Stub: returns `b""` (silence) if ELEVENLABS_API_KEY absent
- Sarvam Bulbul for Telugu: NOT YET IMPLEMENTED (Phase 2B C4)

---

## Config / env vars for voice
```
PLIVO_AUTH_ID         — Plivo account auth ID
PLIVO_AUTH_TOKEN      — Plivo account auth token (signature verification)
PLIVO_PHONE_NUMBER    — DID to point at the answer webhook
PLIVO_BUSINESS_ID     — single-tenant: the business_id that owns the Plivo number
PUBLIC_BASE_URL       — ngrok/prod HTTPS URL Plivo posts to (e.g. https://abc.ngrok.io)
SARVAM_API_KEY        — Telugu STT (Saarika v2) + TTS (Bulbul, Phase 2B)
DEEPGRAM_API_KEY      — English/Hindi STT (Nova-2)
ELEVENLABS_API_KEY    — English/Hindi TTS (Flash, Phase 2B streaming)
ANTHROPIC_API_KEY     — Claude (ai_engine.py); falls back to stub heuristic if absent
AI_MODEL              — default "claude-sonnet-4-6"
```

---

## Phase 2B plan (streaming turn loop)
What needs to be built next to make it actually talk:

1. **MPC migration (B2)**: switch answer webhook to return Plivo MPC XML; backend adds `ai-agent` participant via API pointing at our stream WS; add `mpc_uuid` column (migration 0005)
2. **Streaming STT (C2)**: Deepgram live WS (interim+final, VAD) for en/hi; Sarvam streaming WS for te; transcode Plivo mu-law → 16kHz PCM; END_SPEECH event triggers turn
3. **Turn loop (C3)**: on END_SPEECH → `ai_engine.run_turn()` (streaming response) → sentence-fragment to TTS
4. **Streaming TTS (C4)**: ElevenLabs low-latency streaming for en/hi; Sarvam Bulbul WS for te; barge-in = close socket + flush
5. **Barge-in (C5)**: START_SPEECH during playback → cancel LLM stream + TTS within <500ms; log `barge_in` call_event

---

## Compliance guards
- Outbound window: 09:00–21:00 IST (`compliance.is_within_outbound_hours()` — verified boundary cases; NOT wired to any endpoint yet)
- NCPR/DND scrub before any outbound campaign
- 140-series caller ID (travel = promotional; 1600-series is BFSI-only)
- WebSocket disconnects: log every disconnect with call_id; mark travel_calls.status = 'failed' on abrupt disconnect (implemented in webhooks_voice.py)
