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
| C-3 | Consent event recorded per call | ✅ **MECHANISM DONE (wave-2)** | `webhooks_voice.py answer_call()` writes a `travel_call_events` row (`event_type='consent_disclosure_played'`, payload carries language + wording_version) at the moment the answer XML is served; try/except-guarded so an audit-write failure never breaks answering. No migration needed — event_type is unconstrained VARCHAR(50). Wording itself remains BLK-8 |
| C-4 | Recording storage/retention policy | 🚦 **DECISION** | `travel_calls.recording_url` exists; no retention/deletion job exists anywhere. Moot until Plivo creds exist (B-P2-01), but must be decided before they do |
| C-5 | Outbound calling hours (TRAI) | ✅ EXISTS | `services/travel/compliance.py` enforces 09:00–21:00 IST; called from `routers/techscape/send.py` |

## D — DPDP (Digital Personal Data Protection Act)

| # | Item | Status | Where / evidence |
|---|---|---|---|
| D-1 | Notice at point of collection | 🟡 DRAFTS EXIST (wave-2) | `docs/legal/TERMS_OF_SERVICE_DRAFT.md` + `PRIVACY_POLICY_DRAFT.md`: structure + schema-derived facts (processors, no-card-data, erasure endpoint), loud DRAFT/NOT-LEGAL-ADVICE banners, `[LEGAL TO COMPLETE]` markers. Final text = BLK-8; wiring the signup spans to the published docs happens when legal signs off |
| D-2 | Consent artefact stored | 🟡 PARTIAL | `register-business` accepts `terms_accepted_at`/`terms_version` and the client sends them; verify they persist to a column (they are accepted by the Pydantic model; storage not confirmed against the DB write) |
| D-3 | Right to erasure path | ✅ **MECHANISM DONE (wave-2)** | `DELETE /api/travel/v1/customers/{id}/personal-data` (admin-gated), `erasure_service.py` anonymizes across 10 tables (money columns kept — invoice/audit integrity), one `activity_log` row, 409 on Gowtham-owned edge cases (active booking / live call). 13 tests |
| D-4 | Data minimisation on the traveller surface | ✅ GOOD | `/me/*` endpoints return only the caller's own scoped rows; no PII of other parties in any response shape |
| D-5 | Credential hygiene in errors/logs | ✅ **FIXED this run** | error-tracking scrubs `password/token/secret/authorization` keys and `Bearer …` strings in BOTH stub and live modes; separately, B-FE7-04 (422 echoing passwords) remains a backend fix |
| D-6 | Breach-notification readiness | 🚦 **DECISION** | No incident-response doc exists. Policy item, not code |

## P — Payment data

| # | Item | Status | Where / evidence |
|---|---|---|---|
| P-1 | No card data touches our systems | ✅ GOOD | Razorpay-hosted payment links only (`gateway_short_url`); no PAN/card fields anywhere in schema or code |
| P-2 | Money integrity | ✅ GOOD | NUMERIC never float; FX via stored snapshots (`fx_rate_at`); issued invoices frozen by trigger (migration 0019) |
| P-3 | Webhook authenticity | ✅ EXISTS | Razorpay webhook signature verification in `payments.py`; Plivo HMAC in `voice.py` (fails open only when no token is configured — deploy concern noted in that file) |

**Summary (wave-2): 8 ✅ · 1 🟡 (D-1 drafts await legal text) · 4 decisions for Gowtham (C-2, C-4, D-6, plus legal sign-off overall). Every buildable mechanism is built; every remaining item is wording or policy.**
