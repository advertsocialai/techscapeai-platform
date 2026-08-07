# GoGaga — 1-HOUR AUTONOMOUS BUILD SPRINT

Run in Claude Code, repo root, branch `Klara-ai`. Model: claude-sonnet-4-6 · acceptEdits. Timebox: 60 minutes of continuous autonomous work from the moment this prompt starts. No stopping for missing credentials, no stopping for permission on any file/code change. The ONLY things allowed to pause execution within the hour are real 📞 phone-call gates (and even those: if unanswered within ~3 min of prompting, skip and keep building — do not let the loop go idle waiting) and the fixed hard stops below.

## THE ONE RULE THAT MATTERS

Never stop making progress for the full 60 minutes. Every other instruction in this document is in service of that rule. If task N is blocked, don't wait — log it and jump to task N+1, or to the next phase's tasks if this phase is exhausted. At minute 60, whatever state you're in, stop and report. The measure of success is "how much real, evidenced progress happened in 60 minutes," not "did every task fully complete."

## STARTUP (first 3 minutes of the hour)

1. Start a visible timer/log timestamp — note the sprint start time in your first output line, and check elapsed time before starting each new task so you always know how much runway is left.
2. Load skills: `.claude/skills/gogaga-backend`, `gogaga-migrations`, `gogaga-verifier`. If a skill folder is missing, that's a hard stop (see below) — everything else is not.
3. CREDENTIAL SNAPSHOT — do this inline, do not depend on any external file existing:
   * First, check: does `PHASE2_SETUP_GATE_LOOP_PROMPT.md` exist anywhere in the repo (root, docs/, scripts/)? If yes, read and run its Section A as originally intended. If no — proceed with the inline checks below; do not stop, do not ask the human to go find the file, just run this instead:
   * `grep -E "PLIVO_AUTH_ID|PLIVO_AUTH_TOKEN|PLIVO_PHONE_NUMBER|DEEPGRAM_API_KEY|ELEVENLABS_API_KEY|ANTHROPIC_API_KEY|SARVAM_API_KEY|PUBLIC_BASE_URL" .env` — for each present var, do ONE lightweight real API call to confirm it's valid (not just non-empty), masking the value in all output:
      * Plivo: `curl -s -u "$PLIVO_AUTH_ID:$PLIVO_AUTH_TOKEN" https://api.plivo.com/v1/Account/$PLIVO_AUTH_ID/` → 200=valid, else invalid/missing
      * Deepgram: `curl -s -H "Authorization: Token $DEEPGRAM_API_KEY" https://api.deepgram.com/v1/projects` → 200=valid
      * ElevenLabs: `curl -s -H "xi-api-key: $ELEVENLABS_API_KEY" https://api.elevenlabs.io/v1/user` → 200=valid
      * Anthropic: minimal 1-token `POST https://api.anthropic.com/v1/messages` with the key header → 200=valid
      * ngrok/PUBLIC_BASE_URL: `curl -s http://127.0.0.1:4040/api/tunnels` and compare to `.env` value; also curl the public URL itself for reachability
   * Record a simple table (var, PASS/MISSING/INVALID) as the first block of the eventual SPRINT_REPORT.md — this is your only purpose here, a snapshot, not a gate. Do NOT block startup on any result — proceed to the work queue immediately after, regardless of how many are MISSING or INVALID.
   * Optional cleanup for next time: if useful, write a minimal standalone `PHASE2_SETUP_GATE_LOOP_PROMPT.md` into the repo root capturing these same checks, so future sprints (and this one, if re-run) have the file locally. This is a nice-to-have, not required — do it only if it doesn't eat into the 60-minute budget (cap at 2 minutes if attempted).

## WORK QUEUE — PRIORITY ORDER FOR THE HOUR

Attempt in this order. Skip forward past anything blocked; circle back only if you finish everything ahead of the 60-minute mark with time to spare.

**Priority 1 — repo hygiene + anything requiring zero external credentials (do first, guaranteed progress):**

* `.env` gitignore check/fix, any Phase 1/2 TODOs that are pure code (e.g. `access_matrix.py` mint() fix if still open)
* Any PHASE2B or PHASE3 task marked buildable in fixture/mock mode regardless of live keys (e.g. PHASE3 T2 ai_config table + endpoints, T7 phone-routing table, T8 Redis swap — these need no third-party API key at all)

**Priority 2 — tasks unlocked by whichever keys ARE present (per the Section A snapshot):**

* If Anthropic key valid: PHASE2 T5 real-LLM verification, PHASE2B C1 decision + early C3 turn-loop scaffolding
* If Deepgram key valid: PHASE2 T4 real STT verification (English/Hindi)
* If ElevenLabs key valid: PHASE2 T6 TTS build/verification (non-live parts)
* If Plivo Auth ID/Token valid but no number yet: PHASE2B Section B (MPC probe script, provider abstraction code) — buildable and unit-testable without a live number
* If Plivo number + PUBLIC_BASE_URL both valid: attempt the 📞 gates (T2 live, then C6 full conversation) — prompt the human, wait max ~3 min, then continue regardless of response

**Priority 3 — PHASE 3 tasks not gated on live voice** (once PHASE2/2B buildable work is exhausted or blocked): T2 (ai_config), T5 (post-call Sonnet pipeline — testable on mock transcripts even without a live call), T6 (embeddings — testable on existing wiki/transcript data), T7 (phone routing table), T8 (Redis infra swap), T10 (access matrix / hygiene). Skip T1, T3, T4, T9 if they need real-time voice infrastructure not yet proven live.

**Priority 4 — anything left, best effort.**

## BLOCKER RULE (identical to every other GoGaga loop — non-negotiable)

Any missing/invalid credential, unreachable service, or external dependency → log a row to `BLOCKERS.md` (`| ID | Date | Task | Blocker | Blocks | Unblock condition | Owner | Status |`), mark that specific piece BLOCKED, build/verify everything else in that task with real evidence, move on immediately. Never wait. Never guess. Never fabricate evidence.

## HARD STOPS (only these three halt the sprint before 60 minutes)

* A migration would violate the 7-law discipline
* A task requires data deletion or force-push
* A required skill folder is missing

## END OF HOUR — MANDATORY WRAP-UP (last ~5 minutes, budget for this)

Even mid-task, stop new work at minute ~55 and spend the last stretch writing `SPRINT_REPORT.md`:

* §TimeUsed — actual elapsed, any overrun and why
* §Completed — every task/subtask finished this hour, with evidence, tagged to its phase (2/2B/3)
* §PartiallyDone — anything left mid-build, exact state, exact next step to resume it
* §NotAttempted — queue items never reached, and why (ran out of time vs. blocked)
* §BlockersHit — every new BLOCKERS.md row from this hour
* §NextSprintPriority — your recommendation for what the next hour (or next unblock) should tackle first
* Print the full current `BLOCKERS.md` table as the last line of output.

## GUARDRAILS

* Real evidence only — command output, not narration. A task claimed done without pasted evidence is not done.
* Do not skip the Priority 1/repo-hygiene items to rush toward "exciting" voice features — guaranteed progress first, since it's the only kind that can't be wasted by a blocker.
* Don't re-litigate architecture decisions already made in PHASE2B/PHASE3 prompts (e.g. MPC path, embedder choice) — follow them as given.
* If genuinely nothing is buildable (extreme case: no keys at all, nothing in Priority 1 left), say so honestly in SPRINT_REPORT.md rather than inventing busywork — but this should be rare given how much of Priority 1/3 needs no live credentials at all.
