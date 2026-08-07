# GoGaga Blocker Ledger

Single running ledger of everything owed between phases. Updated by every autonomous loop.

| ID | Date | Task | Blocker | Blocks | Unblock condition | Owner | Status |
|---|---|---|---|---|---|---|---|
| B-P2-01 | 2026-08-03 | P2 T2 | PLIVO_AUTH_ID/TOKEN/PHONE_NUMBER absent | Real Plivo answer webhook test | Add Plivo creds to .env + PUBLIC_BASE_URL (ngrok) | Gowtham | OPEN |
| B-P2-02 | 2026-08-03 | P2 T3/T6 | Depends on B-P2-01 | Live media stream + TTS full loop | Unblock B-P2-01 first | Gowtham | OPEN |
| B-P2-03 | 2026-08-03 | P2 T4 | DEEPGRAM_API_KEY/SARVAM_API_KEY absent | Real STT accuracy | Add keys to .env | Gowtham | OPEN |
| B-P2-04 | 2026-08-03 | P2 T5 | ANTHROPIC_API_KEY absent | Real Claude tool-choice/persona quality | Add key to .env | Gowtham | OPEN |
| B-P2-05 | 2026-08-03 | P2 T6 | ELEVENLABS_API_KEY absent | TTS synthesis + barge-in latency test | Add key to .env | Gowtham | OPEN |
| B-P2-06 | 2026-08-03 | P2 T8 | JTI blacklist in-memory (no Redis) | Multi-worker JTI consistency | Provision Redis, add REDIS_URL | Gowtham | OPEN (addressed P3 T8) |
| B-P2B-01 | 2026-08-05 | P2B (all) | Phase 2B never ran — no MPC migration, no streaming STT, no real-time turn loop | P3 T1 live test (MPC audio) | Run Phase 2B first; Plivo + ElevenLabs + Deepgram keys required | Gowtham | OPEN |
| B-P3-01 | 2026-08-05 | P3 T1 | MPC not active (B-P2B-01) + no Plivo creds (B-P2-01) | Live: supervisor monitor/barge/takeover/release audio test (📞) | Unblock B-P2B-01 + B-P2-01 | Gowtham | OPEN |
| B-P3-02 | 2026-08-05 | P3 T3 | ANTHROPIC_API_KEY absent (B-P2-04) + no live calls | Claude-powered real-time suggestions; offline/keyword stub runs | Add ANTHROPIC_API_KEY | Gowtham | OPEN |
| B-P3-03 | 2026-08-05 | P3 T5 | ANTHROPIC_API_KEY absent (B-P2-04) | Claude Sonnet post-call summary (stub mode runs) | Add ANTHROPIC_API_KEY | Gowtham | OPEN |
| B-P3-04 | 2026-08-05 | P3 T8 | Redis not provisioned | Multi-worker call_feed + JTI (in-process fallback runs) | Provision Redis, set REDIS_URL | Gowtham | OPEN |
| B-P3-05 | 2026-08-05 | P3 T9 | SARVAM_API_KEY absent (B-P2-03) + no live call | Telugu end-to-end: Saarika STT + Bulbul TTS + barge-in (📞) | Add SARVAM_API_KEY + unblock B-P2-01 | Gowtham | OPEN |
| B-P3-06 | 2026-08-05 | P3 T9 | PLIVO creds absent (B-P2-01) | Per-participant recording URL stored in travel_calls | Unblock B-P2-01 | Gowtham | OPEN |
| B-P3-07 | 2026-08-05 | P3 ENV | Colima/Supabase stack not running at loop start | Live regression check + migration application | `colima start && supabase start -x vector,logflare` | Gowtham | OPEN |
| DEBT-01 | 2026-08-05 | P3 T3/T4 | LATENCY_INSUFFICIENT_FOR_INLINE — Phase 2B never ran; no mouth-to-ear baseline; T3/T4 built in MOCK/OFFLINE mode | Inline suggestions/sentiment inside voice turn loop | Run Phase 2B, measure headroom_ms; if ≥300ms → upgrade to synchronous inline calls | Gowtham | DEBT |
| DEBT-02 | 2026-08-05 | P2 T8 | In-memory JTI blacklist does not survive restart or multiple workers | Auth security under multi-worker deploy | Provision Redis + unblock B-P3-04 → P3 T8 Redis migration completes this | Gowtham | DEBT (addressed P3 T8) |
| DEBT-03 | 2026-08-05 | P2 | access_matrix.py mint() previously broken — now fixed in P3 T10 | — | Fixed | Gowtham | RESOLVED in P3 T10 |
