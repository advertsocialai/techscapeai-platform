# ⚠️ DRAFT — NOT LEGAL ADVICE — PENDING LEGAL REVIEW (BLK-8) ⚠️

> Engineering-authored SKELETON for a DPDP-oriented privacy policy: headings
> plus FACTS pulled from the actual schema and code, so the lawyer drafts
> against reality instead of guesses. Every `[LEGAL TO COMPLETE]` marker is
> a lawyer's paragraph. Do not link this from the app; D-1 closes only when
> a reviewed version replaces it.

# Privacy Policy — GoGaga / TechScape AI (DRAFT SKELETON)

## 1. Who processes your data

- Data fiduciary/processor split between the platform operator and each
  travel agency (agencies are the traveller-facing businesses; the platform
  is multi-tenant): **[LEGAL TO COMPLETE — this classification drives the
  whole document]**
- Contact / grievance officer (DPDP requirement): [LEGAL TO COMPLETE]

## 2. What we collect (factual, per the actual schema)

- **Customer/traveller profile** (`travel_customer_profiles`): full name,
  email, phone, language, travel preferences, past trips, family profile,
  free-text notes, last stated intent.
- **Leads** (`travel_leads`): phone, the verbatim first message
  (`raw_message`), stated intent, destination/budget/party-size hints,
  and a semantic embedding derived from the message.
- **Calls** (`travel_calls` / `travel_transcripts`): call metadata
  (numbers, duration, timestamps), recording URL (when recording is
  enabled), full transcripts (original + translated), per-turn sentiment
  scores, transcript embeddings, AI-generated call summaries.
- **Messaging** (`whatsapp_outbox`): WhatsApp recipient number and message
  payloads sent on the agency's behalf.
- **Bookings/itineraries**: trip details, dates, party size, costs,
  free-form metadata.
- **Payments** (`payment_links`): amount, currency, link status, gateway
  identifiers. **No card/UPI data — payment credentials are entered on
  Razorpay-hosted pages only and never reach this platform.**
- **Agency staff accounts** (`ts_users`): name, email, role, hashed
  password; audit trail of actions (`activity_log`).

## 3. Where it comes from

- Directly from you (calls, WhatsApp, web forms); generated about you by
  AI processing (transcripts, summaries, sentiment, embeddings); from the
  agency you deal with.

## 4. Why we process it (purposes / lawful basis)

- Responding to travel enquiries, preparing itineraries, operating
  bookings, payment collection, service quality (call review), follow-ups.
- Consent notice for call recording: an announcement plays before
  processing starts and a per-call `consent_disclosure_played` event is
  stored (language + wording version). Wording: **[LEGAL TO COMPLETE — BLK-8]**
- Lawful-basis mapping per purpose (DPDP consent vs legitimate use):
  [LEGAL TO COMPLETE]

## 5. Who else touches it (processors / sub-processors — factual)

| Provider | Used for |
|---|---|
| Supabase | Database + storage hosting |
| Plivo | Telephony (calls, media streams) — India-domestic voice |
| Razorpay | Payment links (hosted checkout; card data stays with Razorpay) |
| ElevenLabs | Text-to-speech voices |
| Sarvam | Speech-to-text / TTS (Telugu & code-mix) |
| Deepgram | Speech-to-text (English/Hindi) |
| Anthropic | In-call AI, extraction, sentiment (Claude) |
| Meta (WhatsApp Cloud API) | WhatsApp messaging (when enabled) |

- Cross-border transfer analysis for the non-India providers:
  [LEGAL TO COMPLETE]

## 6. How long we keep it (retention)

- **PENDING (BLK-7): no retention policy is decided yet.** Engineering
  facts: no automatic deletion job exists; recordings/transcripts persist
  until erased; a backup mechanism with a configurable retention window is
  prepared (scripts/backup_db.sh) awaiting the same decision.
- Retention table per data category: [LEGAL TO COMPLETE after BLK-7]

## 7. Your rights (DPDP)

- **Erasure**: implemented — an admin runs
  `DELETE /api/travel/v1/customers/{id}/personal-data`, which anonymizes
  personal fields across profiles, leads, transcripts, recordings,
  itineraries, incidents and messaging rows. **Financial records (payment
  amounts, invoices, booking totals) are retained** for invoice/audit
  integrity; the person is removed, not the transaction.
- Access / correction / grievance / nomination rights and request
  channels: [LEGAL TO COMPLETE]
- Verification of requester identity: [LEGAL TO COMPLETE]

## 8. Security (factual)

- Row-level security on all tables with API-layer authorization; role-based
  access control; JWT auth with short-lived tokens; passwords hashed;
  secrets scrubbed from error logs; webhook signature verification
  (Razorpay, Plivo).
- Breach notification procedure: **[LEGAL TO COMPLETE — D-6, no
  incident-response document exists yet]**

## 9. Children's data

- [LEGAL TO COMPLETE — family_profile may describe minors travelling]

## 10. Changes to this policy

- [LEGAL TO COMPLETE]

---
*Document version: draft-1 (2026-08-10, engineering skeleton). Facts above
were read from database/travel_schema.sql, supabase/migrations/ and api/app/
on 2026-08-10 — re-verify before publication.*
