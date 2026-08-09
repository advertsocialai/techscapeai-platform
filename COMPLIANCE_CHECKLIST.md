# Compliance checklist — assessed against the actual codebase, 2026-08-09

Assessment, not guessing: every row cites where in the code the item stands
today. Items marked **DECISION** are judgment calls that go to Gowtham via
BLOCKERS.md, never guessed here. This is an engineering review, **not legal
advice** — a lawyer signs off on the final wording and policy items.

## C — Call recording & transcription (India)

| # | Item | Status | Where / evidence |
|---|---|---|---|
| C-1 | Caller told the call is recorded/transcribed | ✅ **FIXED this run** | `voice.py stream_xml()` now plays `CONSENT_ANNOUNCEMENT` **before** the media stream opens — a caller who hangs up on hearing it is never transcribed. Previously: nothing, anywhere in the flow |
| C-2 | Exact announcement wording legally reviewed | 🚦 **DECISION (BLK-8)** | Present wording is plain-English engineering copy. Telugu/Hindi versions also needed — the announcement currently plays in English regardless of `ai_config.languages` |
| C-3 | Consent event recorded per call | 🔴 GAP | Nothing writes a "disclosure played" marker to `travel_calls`/`travel_call_events`. Cheap to add (an event row when the answer XML is served); logged in BLOCKERS as follow-up, not done this run because the event taxonomy is Gowtham-owned |
| C-4 | Recording storage/retention policy | 🚦 **DECISION** | `travel_calls.recording_url` exists; no retention/deletion job exists anywhere. Moot until Plivo creds exist (B-P2-01), but must be decided before they do |
| C-5 | Outbound calling hours (TRAI) | ✅ EXISTS | `services/travel/compliance.py` enforces 09:00–21:00 IST; called from `routers/techscape/send.py` |

## D — DPDP (Digital Personal Data Protection Act)

| # | Item | Status | Where / evidence |
|---|---|---|---|
| D-1 | Notice at point of collection | 🟡 PARTIAL | Signup shows Terms/Privacy checkboxes (`TermsPage.tsx`) but the linked documents **do not exist** — the spans navigate nowhere |
| D-2 | Consent artefact stored | 🟡 PARTIAL | `register-business` accepts `terms_accepted_at`/`terms_version` and the client sends them; verify they persist to a column (they are accepted by the Pydantic model; storage not confirmed against the DB write) |
| D-3 | Right to erasure path | 🔴 GAP | No endpoint or job deletes a customer's personal data. `travel_customer_profiles` rows have no deletion story |
| D-4 | Data minimisation on the traveller surface | ✅ GOOD | `/me/*` endpoints return only the caller's own scoped rows; no PII of other parties in any response shape |
| D-5 | Credential hygiene in errors/logs | ✅ **FIXED this run** | error-tracking scrubs `password/token/secret/authorization` keys and `Bearer …` strings in BOTH stub and live modes; separately, B-FE7-04 (422 echoing passwords) remains a backend fix |
| D-6 | Breach-notification readiness | 🚦 **DECISION** | No incident-response doc exists. Policy item, not code |

## P — Payment data

| # | Item | Status | Where / evidence |
|---|---|---|---|
| P-1 | No card data touches our systems | ✅ GOOD | Razorpay-hosted payment links only (`gateway_short_url`); no PAN/card fields anywhere in schema or code |
| P-2 | Money integrity | ✅ GOOD | NUMERIC never float; FX via stored snapshots (`fx_rate_at`); issued invoices frozen by trigger (migration 0019) |
| P-3 | Webhook authenticity | ✅ EXISTS | Razorpay webhook signature verification in `payments.py`; Plivo HMAC in `voice.py` (fails open only when no token is configured — deploy concern noted in that file) |

**Summary: 6 ✅ · 3 🟡/🔴 gaps (C-3, D-1, D-3) · 4 decisions for Gowtham (C-2, C-4, D-6, plus legal sign-off overall).**
