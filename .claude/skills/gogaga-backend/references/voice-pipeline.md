# GoGaga Voice Pipeline Reference (Phase 2–3)

## Architecture (India domestic — NOT Twilio)
```
Caller (+91) → Plivo India (140-series CLI, DLT-registered)
  → POST /webhook/voice (verify Plivo signature) → XML <Stream bidirectional="true">
  → WS /webhook/stream (audio frames both directions)
  → Orchestrator (Pipecat or custom in services/voice.py)
      → Language detect: first 2–3s, ≥3-word match, confidence >0.85, ~500ms debounce
      → STT: Sarvam Saaras/Saarika (Telugu, code-mixed) | Deepgram Nova-3 (English/Hindi)
      → Claude via services/ai_engine.py (tool-calling; config from ai_config table)
      → TTS: Sarvam Bulbul v3 (Telugu/Hindi) | ElevenLabs Flash (premium English)
  → sentence-level streamed audio back
  → every turn → transcripts row; lifecycle → calls row; new phone → leads row
  → broadcast on WS /ws/calls/{call_id}
```

## Hard rules
- **Twilio is forbidden for +91 domestic** — it cannot legally carry India-to-India calls. Plivo/Exotel only. (Twilio OK only for future international/NRI traffic.)
- **Latency budget**: ≤1.1s median, ≤1.4s p95 mouth-to-ear. Log per-hop every turn: stt_ms, llm_ttft_ms, tts_ttfb_ms.
- **Streaming everywhere**: pipe Claude tokens to TTS sentence-by-sentence; first audio plays while Claude still generates. Pre-warm TTS connections (keepalive).
- **Barge-in sequence** (speech detected during playback): stop audio → flush TTS buffer → abort Claude stream → cancel open tool calls → re-run inference.
- **Engine-agnostic transcripts**: same schema regardless of STT source; record stt_engine + language per call.

## ai_engine.py rules
- Structured extraction (destination/dates/budget/group_size) via Claude tool calling ONLY. Never regex/free-text parse.
- Dynamic data (packages, prices, availability) exposed as tools (get_packages(), get_availability()). NEVER embedded in the system prompt — prevents hallucinated offers.
- System prompt: short sentences, no filler ("Certainly!", "Absolutely!") → lower TTFT.
- Personality/rules/flow read from ai_config table per branch. Zero hardcoded prompts.

## Takeover (P3)
- Conference-bridge pattern, NOT SIP REFER (REFER drops the media fork → live transcript dies).
- Sequence: pre-create conference room → move caller in → dial agent into same room → detach AI TTS output cleanly → KEEP transcription fork alive (whisper + live transcript continue) → calls.mode = 'conference'.

## Compliance guards (enforce in code)
- Outbound calls/messages: 09:00–21:00 IST window only
- NCPR/DND scrub before any outbound campaign
- 140-series caller ID (travel = promotional; 1600-series is BFSI-only, not us)

## Failure handling
- STT/TTS API failure mid-call: degrade gracefully (retry once, then apologize-and-callback flow). Never crash the live call.
- WebSocket disconnects fail silently — monitor and alert; log every disconnect with call_id.
