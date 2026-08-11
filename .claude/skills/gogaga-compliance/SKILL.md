---
name: gogaga-compliance
description: India-specific regulatory patterns (TRAI call-recording consent, DPDP Act data-subject rights) for the GoGaga voice/data platform. ALWAYS use this skill when touching call-recording/consent flow, outbound calling-hours logic, data erasure, PII handling, terms/privacy-policy wiring, or any DPDP/TRAI-adjacent code. Trigger on: consent, DPDP, TRAI, erasure, right to be forgotten, retention, breach, PII, personal data, calling hours, CONSENT_WORDING_VERSION. This is an engineering-review skill, not legal advice — final wording/policy items always route to Gowtham as a 🚦 decision in BLOCKERS.md, never guessed in code or copy.
---

# GoGaga Compliance (India) — engineering patterns, not legal opinions

This skill exists because compliance mechanisms in this codebase are **finished and correct**, but the words and policy choices layered on top are legal decisions this skill must never make unilaterally. Read `COMPLIANCE_CHECKLIST.md` at session start for the live status table (C-*/D-*/P-* rows) before changing anything in this space — it's the source of truth, cited to code, refreshed each wave.

## 1. Call-recording consent (TRAI)

- **Mechanism (done, keep it this way):** `services/travel/voice.py: stream_xml()` plays `CONSENT_ANNOUNCEMENT` **before** the media `<Stream>` opens — a caller who hangs up on hearing the disclosure is never transcribed. Never reorder this so the stream opens first "to save latency" — the ordering is the compliance property, not an implementation detail.
- **Audit trail (done):** `webhooks_voice.py: answer_call()` writes a `travel_call_events` row (`event_type='consent_disclosure_played'`, payload `{language, wording_version}`) at the moment the disclosure plays, wrapped in try/except so an audit-write failure never blocks the call from answering. If you touch this path, preserve both properties: the write happens, and its failure is non-fatal to the call.
- **Wording versioning:** `CONSENT_WORDING_VERSION` (currently `"draft-1"`) is bumped **every time the disclosure text changes**, so historical call events stay attributable to the exact wording a caller heard. Never edit `CONSENT_ANNOUNCEMENT` without bumping this constant in the same change — an unversioned wording edit silently corrupts the audit trail's meaning for every past call.
- **What's still open (route to Gowtham, don't guess):** the actual legal wording is placeholder engineering copy (`BLK-8`) and plays in **English only regardless of `ai_config.languages`** — Telugu/Hindi versions don't exist yet. Do not write te/hi translations yourself; that's the reviewed-wording item, not a code task.
- **Calling hours:** `services/travel/compliance.py` already enforces 09:00–21:00 IST for outbound, called from `routers/techscape/send.py`. If any new outbound-calling code path is added, it must call through this same check — never re-implement calling-hours logic inline.

## 2. DPDP Act (Digital Personal Data Protection)

- **Right to erasure (done):** `DELETE /api/travel/v1/customers/{id}/personal-data`, admin-gated, implemented in `erasure_service.py` — anonymizes across ~10 tables, deliberately **keeps money columns** (invoice/audit integrity overrides erasure there — this is correct, not a bug), writes one `activity_log` row, returns 409 on edge cases Gowtham owns (active booking / live call in progress — don't silently succeed on those, the 409 is intentional). 13 tests cover this; extend the test suite if you extend the erasure scope, don't just extend the anonymization list.
- **Data minimisation:** every `/me/*` traveller endpoint returns only that traveller's own scoped rows — if you add a new `/me/*` field, check it can't leak another party's PII (co-traveller names on a shared booking, agent internal notes, etc.) before shipping.
- **Credential hygiene in logs/errors:** error-tracking scrubs `password/token/secret/authorization` keys and `Bearer …` strings in both stub and live observability modes. Any new logging call must go through the same scrubbing path — never `logger.info(f"...{raw_request_body}...")` on anything that might carry a password or token field. (Separately tracked: `B-FE7-04`, a 422 validation-error echo that leaks submitted passwords back to the client — fix that the same way if you touch that code.)
- **Notice at collection:** `docs/legal/TERMS_OF_SERVICE_DRAFT.md` / `PRIVACY_POLICY_DRAFT.md` exist with structure + schema-derived facts and loud DRAFT/NOT-LEGAL-ADVICE banners and `[LEGAL TO COMPLETE]` markers — never remove those banners or fill in the bracketed sections yourself; that's the same BLK-8 legal-sign-off gate as the call-consent wording.
- **Consent artefact storage:** `register-business` accepts and the client sends `terms_accepted_at`/`terms_version` — if you touch signup, verify these actually persist to a column rather than assuming the Pydantic model accepting them means they're stored; this was flagged as unconfirmed.
- **Breach notification:** no incident-response doc exists yet — this is a pure policy item for Gowtham, not something to scaffold in code speculatively.

## 3. Payment data

- No PAN/card fields exist anywhere in the schema or code, and that must stay true — Razorpay-hosted payment links only (`gateway_short_url`). If any future change would touch raw card data, stop and flag it; that's a PCI-scope decision far above this repo's current design.
- Money is always `NUMERIC`/`Decimal`, never `float`; FX conversions always go through stored `fx_rate_at` snapshots so a historical invoice never silently re-prices.

## 4. The pattern to follow for any new compliance-adjacent feature

1. Check `COMPLIANCE_CHECKLIST.md` for whether a row already exists for this concern.
2. If the *mechanism* is missing, build it — that's ordinary engineering work.
3. If the *wording or policy choice* is missing, don't invent it — add/update a `BLK-*` or `DECISION` entry (coordinate with `gogaga-golive-roadmap`) and leave a clearly marked placeholder in code/copy, versioned the same way `CONSENT_WORDING_VERSION` is, so swapping in the real text later is a one-line change with full audit continuity.
