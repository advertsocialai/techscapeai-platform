# ⚠️ DRAFT — NOT LEGAL ADVICE — PENDING LEGAL REVIEW (BLK-8) ⚠️

> This is an engineering-authored SKELETON: structure plus platform facts a
> lawyer needs, nothing more. No section below is usable wording. Every
> `[LEGAL TO COMPLETE]` marker is a paragraph a qualified lawyer must write.
> Do not link this from the app; D-1 closes only when a reviewed version
> replaces it.

# Terms of Service — GoGaga / TechScape AI (DRAFT SKELETON)

## 1. Who we are / definitions

- Operator entity name, registered address, CIN/GST: **[LEGAL TO COMPLETE]**
- Two user populations exist in the product and need distinct terms:
  - **Agency users** (travel-agency staff: super_admin/admin/agent/viewer
    roles, dashboard at agency-dashboard/)
  - **Travellers** (customers of those agencies: Klara customer-app, `/me/*`
    endpoints; authenticated by traveller tokens, not agency accounts)
- Definitions of "Platform", "Agency", "Traveller", "Content": [LEGAL TO COMPLETE]

## 2. The service (factual inputs)

- AI-assisted travel-sales platform: lead capture (WhatsApp/web/phone),
  AI voice calls (inbound answering with optional human takeover),
  itinerary generation, follow-ups, payment links, dashboards.
- AI-generated content is present throughout (itineraries, call replies,
  summaries, suggestions). Accuracy disclaimer for AI output:
  **[LEGAL TO COMPLETE]**
- Human takeover: agency staff can monitor/join live AI calls.

## 3. Accounts and acceptable use

- Account tiers and responsibility for credentials: [LEGAL TO COMPLETE]
- Acceptable-use limits (no unlawful marketing, TRAI/DND compliance for
  outbound calling — the platform enforces a 09:00–21:00 IST outbound
  window in code): [LEGAL TO COMPLETE]

## 4. Payments (factual inputs)

- Payments run through **Razorpay-hosted payment links** — card/UPI data is
  entered on Razorpay's pages and **never touches this platform** (no
  PAN/card fields exist in schema or code).
- Amounts are recorded with fixed FX snapshots; issued invoices are frozen
  (immutable) at issue time.
- Refunds/cancellation policy between agency and traveller: **[LEGAL TO
  COMPLETE — likely per-agency, platform's role to be defined]**

## 5. Call recording and AI processing

- Calls may be recorded and transcribed; a disclosure announcement plays
  before any processing starts and the platform records a per-call consent
  event (`consent_disclosure_played`, versioned wording).
- Exact consent wording + Hindi/Telugu translations: **[LEGAL TO COMPLETE
  — BLK-8]**

## 6. Data

- Data handling is described in the Privacy Policy (see
  PRIVACY_POLICY_DRAFT.md — same review gate).
- Erasure requests: the platform implements
  `DELETE /api/travel/v1/customers/{id}/personal-data` (anonymization;
  financial records retained). Contact route for requests: [LEGAL TO COMPLETE]

## 7. Liability, warranties, indemnity

- [LEGAL TO COMPLETE — entirely legal drafting; no engineering input]

## 8. Termination / suspension

- [LEGAL TO COMPLETE]

## 9. Governing law and disputes

- Expected: India; jurisdiction/arbitration clause: [LEGAL TO COMPLETE]

## 10. Changes to these terms

- Versioning mechanism exists in code (`terms_version` +
  `terms_accepted_at` accepted at registration). Notice period and
  re-acceptance policy: [LEGAL TO COMPLETE]

---
*Document version: draft-1 (2026-08-10, engineering skeleton). Supersede on
legal review — do not edit wording piecemeal without bumping version.*
