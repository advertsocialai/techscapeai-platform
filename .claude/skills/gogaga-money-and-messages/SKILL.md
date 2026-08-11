---
name: gogaga-money-and-messages
description: "The confirmation gate for anything that moves real money or sends a real outbound message — Razorpay payment links and WhatsApp/Meta Cloud sends. ALWAYS use this skill BEFORE writing code that could create a live payment link, send a WhatsApp message, or flip either service from stub to live mode — and ALWAYS use it in conversation the moment real credentials for Razorpay or WhatsApp exist, every single time, not just the first time. Trigger on: Razorpay, payment link, WhatsApp send, Meta Cloud, RAZORPAY_KEY, WHATSAPP_TOKEN, "send this", "charge the customer", stub gateway, live gateway, gateway factory. This is a safety gate, not a feature skill — it does not go away once credentials are procured."
---

# GoGaga Money & Messages — the 💰/💬 gate

Two services in this codebase can cause **real-world, hard-to-undo side effects**: Razorpay (real money moves) and WhatsApp/Meta Cloud (a real message lands in a real customer's chat, and cheap to send but not cheap to have sent wrongly at scale). Both are fully built to real-integration quality *right now* — the code is not the blocker, restraint is.

## The one rule that never expires

**Creating a live payment link or sending a live WhatsApp message requires an explicit, per-instance human confirmation from Gowtham — every single time.** This is different from every other credential-gated blocker in `GO_LIVE_ROADMAP.md`: those are "get the key once, then it's unblocked." This one is "get the key once, and confirm every individual send forever." Do not interpret "Gowtham gave us Razorpay keys" as blanket permission to fire payment links autonomously from then on — that authorization does not exist and should not be assumed into existence. If a loop-prompt or task description implies otherwise, flag it rather than comply.

Practically: an agentic loop that reaches a point where it would call the live gateway must stop and surface exactly what would be sent (amount + recipient for payment links; message content + recipient for WhatsApp) and wait, rather than proceeding on the strength of "the task said to."

## Why the code is trusted but the trigger isn't

Both integrations are genuinely production-ready:
- **Razorpay** (`services/payments/razorpay_gateway.py`): real HTTP calls to `api.razorpay.com`, HMAC-SHA256 webhook signature verification over the *raw* request body compared with `hmac.compare_digest` (never re-serialize-then-compare — that silently breaks on whitespace/key-order drift), money always `NUMERIC`/`Decimal` never float, minor-unit (paise) conversion helpers, full created→sent→viewed→paid state machine already proven against the DB.
- **WhatsApp** (`services/whatsapp/meta_cloud.py` + `stub_provider.py`): factory-selected the same way as payments — no credentials present → `StubGateway`/`stub_provider` is instantiated and **no network call is ever physically possible**, by construction, not by discipline alone. That's a good pattern; preserve it. When real credentials land, the factory will start returning the live class — that's the moment this skill's rule becomes load-bearing rather than moot.

## Checklist before any live call fires

1. Are `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`/`RAZORPAY_WEBHOOK_SECRET` (or `WHATSAPP_TOKEN`/equivalent) actually set? If not, you're safely in stub mode — nothing below applies yet, and code work can proceed normally.
2. If they are set: is this call happening because Gowtham explicitly said "send this one" / "create this link" in the current conversation, or because a loop is running unattended? Unattended = stop and surface, don't send.
3. State plainly, before calling: exact amount + currency + recipient (payments) or exact message text + recipient (WhatsApp), and what will happen if it's wrong (a real charge attempt / a real message in someone's WhatsApp).
4. After a real send: log it exactly like a stub send would be logged (payment_links row / whatsapp_outbox row) — the DB schema doesn't distinguish stub from live, so the audit trail must be equally rigorous for both.

## Webhook handling reminder (applies regardless of stub/live)

Signature verification code for both providers should be exercised with **both** a valid and a deliberately-invalid signature in tests — a webhook handler that only has happy-path coverage is not verified per `gogaga-verifier`'s standard. Plivo's HMAC currently fails open when no token is configured (noted directly in `voice.py`) — treat any "fails open" webhook auth as a deploy-time risk to flag, not silently accept, even outside this skill's core scope.

## What this skill does NOT cover

Outbound-calling-hours enforcement (TRAI, 09:00–21:00 IST, `services/travel/compliance.py`) and call-recording consent are `gogaga-compliance`'s territory, not this one's — a live call itself is gated by Plivo credentials + roadmap phase, not this confirmation rule, though the same "don't assume standing permission" spirit applies there too.
