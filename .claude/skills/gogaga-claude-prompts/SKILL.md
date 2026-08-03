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
