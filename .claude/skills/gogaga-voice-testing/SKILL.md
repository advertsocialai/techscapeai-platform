---
name: gogaga-voice-testing
description: Testing patterns for the GoGaga voice pipeline (Plivo media streams, Sarvam/Deepgram STT, Claude engine, ElevenLabs TTS) WITHOUT needing a real phone call for every iteration. ALWAYS use this skill when testing, debugging, or verifying anything in the voice pipeline — webhooks, media streams, STT, TTS, latency, barge-in, or the WS live feed. Trigger on: test the call, voice webhook, media stream, simulate call, replay audio, mock Plivo, latency check, VOICE_TURN. Real 📞 calls remain mandatory at phase gates; these patterns cover the 50 iterations between them.
---

# GoGaga Voice Testing (starter — enrich with real findings during Phase 2)

Principle: **real calls prove gates; simulated inputs drive iteration.** Every component must be testable without dialing.

## Test pyramid for the pipeline
1. **Unit (no network):** ai_engine on canned transcripts · XML response shape · signature calc
2. **Component (one provider live):** audio file → STT accuracy · text → TTS audio out
3. **Simulated call (no telephony):** replay recorded frames into the WS endpoint
4. **Real call 📞 (gates only):** T2/T3/T4/T6/T7 verification + phase gate

## Patterns

### Mock Plivo signature (webhook tests without Plivo)
Plivo V2 signature = Base64(HMAC-SHA256(auth_token, url + nonce)). Build a helper that signs a fake request with YOUR auth token so the verifier passes; also send one deliberately-bad signature expecting 403. Keep the helper in scripts/ once written (T2 will produce it — save it here).

### Media stream replay (the workhorse)
Record ONE real call's frames early (log raw base64 media messages to a .jsonl in T3). Then `scripts/replay_stream.py` (starter included) connects to ws://…/webhook/stream and replays start→media(×N)→stop with original timing. Iterate on STT/AI/TTS all day without dialing. Re-record after any Plivo config change.

### STT accuracy harness
Keep 3–5 reference audio clips (English, Telugu, code-mixed; record yourself reading known scripts at 8kHz). Feed via replay; diff transcript rows vs the known text; track WER-ish score per engine per run. Sarvam-vs-Deepgram routing decisions come from THIS data, not vibes.

### TTS loop-back check
Pipe TTS output frames to a .wav file in dev mode AND to the stream — listen without calling. Assert first-audio-byte time (tts_ttfb_ms) from logs.

### Latency assertions
`grep VOICE_TURN api.log | tail -50` → compute median/p95 per hop (stt_ms, llm_ttft_ms, tts_ttfb_ms, total_ms). Fail the check if median total_ms > 1100 or p95 > 1400. Never average away spikes — p95 matters for feel.

### Barge-in test sequence
During replayed playback, inject a media frame burst mid-TTS → assert: TTS stopped, buffer flushed, Claude stream aborted, new inference started. Log markers for each step; the test greps for the 4 markers in order.

### WS feed testing
gogaga-verifier's ws_probe.py during a replayed call: transcript messages arrive with monotonic seq; agent-role token sees assigned-only; viewer rejected. Kill the WS mid-call → server logs the disconnect (silent-failure guard).

### Failure injection
Stub a provider 500 (env flag or monkeypatch): call must survive with retry-once → apology flow. One test per provider (STT, LLM, TTS).

## Rules
- Never mark a voice task done on replay alone if the task is a 📞 gate.
- Every new bug found on a real call → add a replay-based regression test here.
- ENRICH THIS SKILL: after T6 passes, append the actual commands/scripts that worked under "## Learned during Phase 2".
