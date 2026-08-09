---
name: gogaga-claude-prompts
description: The product-side AI prompts, tool schemas, and generation rules for GoGaga — the Claude voice engine persona, lead-extraction tool schemas, sentiment rubric, whisper suggestions, and the Gemini templates for WhatsApp/briefs. ALWAYS use this skill when writing or editing ANY prompt, system message, tool schema, or LLM call inside the product code (services/travel/*, ai_engine work, sentiment, summaries). Trigger on: personality prompt, system prompt, tool schema, extraction, sentiment scoring, whisper, WhatsApp summary, morning brief, Gemini template. Prompts live HERE, versioned — never scattered as inline strings.
---

# GoGaga Product Prompts (starter — refine from real call logs in Phase 2/3)

Cost routing law (blueprint §7): **Claude** = live voice replies, sentiment, whisper ONLY. **Gemini Flash** = WhatsApp replies, summaries, briefs, follow-up drafts. Never swap them.

## Rules for all product prompts
1. Prompts and tool schemas live in `references/` here + a single `prompts.py` (or ai_config rows) in code — never inline strings in handlers.
2. Voice replies: SHORT sentences, no filler ("Certainly!", "Absolutely!"), no URLs, no lists — it's spoken audio. Target ≤2 sentences per turn unless summarizing.
3. **Dynamic data never in the prompt** — packages, prices, availability come through tools. Prevents hallucinated offers.
4. Extraction via tool-calling only — never regex/parse free text.
5. Language: mirror the caller (Telugu in → Telugu out; code-mixed is fine and natural). Numbers/dates spoken naturally ("saath july" not "07/07").
6. Every prompt change: note it in references/CHANGELOG.md with the observed behavior that motivated it.

## The pieces (full text in references/voice-persona.md + tool-schemas.md)
- **Voice persona**: "Priya" — GoGaga travel consultant, warm, efficient, culturally aware (Telugu/English), collects destination→dates→pax→budget conversationally, offers packages ONLY from get_packages() results, escalates on request/frustration/high-value.
- **Tools**: extract_lead_details(destination, travel_dates, pax_count, budget_inr, duration_days) · get_packages(destination, budget_inr) · request_human_handoff(reason) · schedule_followup(day_offset, note)
- **Sentiment rubric (P3)**: per chunk → {excitement, intent, price_sensitivity, urgency} each 0–1 with one-line definitions; conservative when text is short.
- **Whisper (P3)**: ≤15-word actionable suggestion to the agent; never repeat the transcript; empty string when nothing useful.
- **Gemini templates (P4)**: post-call WhatsApp summary (customer-facing, ≤1024 chars, 1-2 emojis ok) · Morning Brief (agency-facing) · follow-up ladder D1/D3/D7 drafts.

## Latency discipline
Voice replies: keep max_tokens low (~150), stream always, measure llm_ttft_ms. If TTFT median >375ms, shorten the system prompt before touching anything else.

---

## ⚠️ Reality check — verified against the code 2026-08-09

Everything above was written as a **starter, before the code existed**. Four
claims are now contradicted by what actually shipped. Trust this section over
anything above it, and re-verify before trusting either.

### Gemini does not exist

The cost-routing law assigns WhatsApp replies, summaries, briefs and follow-up
drafts to **Gemini Flash**. There are **zero references to Gemini anywhere in
`api/`**. Everything routes to Claude, or to keyword stubs when no key is set.

That makes the routing law **aspirational, not descriptive**. It is still the
right design — the blueprint chose Gemini for cost, and pushing that volume
through Claude is the expensive default — but do not read this skill and assume
the split is implemented. It is not.

### The sentiment rubric has THREE dimensions, not four

`sentiment_service.score_text()` returns exactly:

```
excitement · intent · price_sensitivity
```

**`urgency` is not computed and never emitted.** A UI or report built against
it renders 0 forever. Do not add it to a prompt or schema expecting it to flow
through.

### There is no `prompts.py`

Rule 1 says prompts live in `references/` here plus "a single `prompts.py` (or
ai_config rows) in code". **No `prompts.py` exists anywhere in `api/`.** The
live path is `travel_ai_config` rows (see the `ai-config` router and the
AI Playbook screen), which is the "or" branch — fine, but the rule reads as
though a file exists when it does not.

### Scores are constants without an API key

With no `ANTHROPIC_API_KEY`, the post-call pipeline writes the **same
`lead_score=40` and `sentiment_score=0.4` on every completed call**. Any prompt
tuning aimed at improving these figures is unmeasurable until a key is set —
you would be tuning against a constant. Set the key first, then tune.
