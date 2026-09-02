# Feature Document — Onboarding

**Branch:** `Klara-ai` @ `2a87dec` · **Validated live:** 2026-09-02 · **Method:** Playwright against the Vercel branch previews

Covers both onboarding funnels: the **Klara customer/business signup** (6 screens) and the **agency dashboard account entry** (4 screens).

Status key: **Works** = exercised live and behaved correctly · **Guarded only** = the route guard was verified, the feature behind it could not be reached · **Broken** = exercised live and failed.

---

## Part A — Klara app onboarding funnel

Route tree from `customer-app/src/App.tsx`. State lives in `OnboardingContext`, persisted to `localStorage["klara_onboarding_state"]`. Steps are gated by `RequireStep`.

### A1 · Screen 1 — Login / Sign-in
- **Route:** `/onboarding/login` (also the target of `/` and of any unmatched route)
- **Elements:** email, password (with show/hide), *Sign In*, *Continue with Google*, *Forgot password*, *Create account*
- **Status:** page **Works** · submit **Broken**

| Check | Result |
|---|---|
| Renders, no uncaught JS | pass |
| `/` redirects here | pass |
| Unknown route redirects here | pass |
| Password visibility toggle present | pass |
| **Sign In → backend** | **fails** — zero XHR reaches any auth endpoint |

The click *is* wired; the request dies at the network layer. Console:

```
Access to XMLHttpRequest at
'https://techscapeai-platform-klara-dev.up.railway.app/api/techscape/v1/auth/login'
… blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present
```

That Railway host returns `Application not found` — it does not exist (RC-2). The UI degrades honestly: *"Could not reach the server. Check your connection and try again."*

**Gap O-1 (BLOCKER):** `VITE_API_URL` points at a dead Railway deployment. No customer can sign in.

### A2 · Screen 2 — Personal info
- **Route:** `/onboarding/personal-info` — the funnel's real entry point
- **Fields:** first name, last name, business email, country code + phone, password, confirm password
- **Status:** **Works** (form, validation, and commit to context all function)

**Gap O-2 (HIGH) — password stored in cleartext.** Completing this step writes the whole state object, `password` included, to `localStorage["klara_onboarding_state"]`. Verified live: the probe password was read back verbatim. Readable by any script on the origin, and left behind on shared machines. → **BLK-15**

### A3 · Screen 3 — Address
- **Route:** `/onboarding/address` · guarded by `RequireStep`
- **Status:** **Guarded only** — cold deep-link correctly redirects to `/onboarding/personal-info`

Field-level behaviour (city/state/postal validation, country handling) is **unvalidated**: reaching it requires completing step 2, and the funnel cannot be completed while O-1 stands.

### A4 · Screen 4 — OTP verification
- **Route:** `/onboarding/otp` · guarded by `RequireStep`
- **Status:** **Guarded only**, and the guard is **bypassable**

**Gap O-3 (HIGH) — verification is decorative.** `RequireStep` reads `otpVerified` from localStorage. Forging it walks straight onto `/onboarding/terms` — confirmed live:

```js
localStorage.setItem('klara_onboarding_state', JSON.stringify({
  email: 'forged@example.com', password: '…', otpVerified: true }))
// → /onboarding/terms renders
```

The deeper problem is server-side: `RegisterBusinessIn` has **no OTP field**, so the backend cannot verify that an address was ever confirmed, whatever the client sends. An account can be created against a never-verified email. → **B-FE7-07**

Whether an OTP is actually delivered (Resend integration, commit `9178ce7`) is **unvalidated** — it needs a live API.

### A5 · Screen 5 — Terms & conditions
- **Route:** `/onboarding/terms` · guarded by `RequireStep` (+ `otpVerified`)
- **Status:** **Guarded only**

Consent capture — terms, age confirmation, marketing opt-in — exists in the context (`termsAccepted`, `ageConfirmed`, `marketingOptIn`) but is **unvalidated end-to-end**. Nothing yet proves consent is transmitted to or stored by the backend, which matters for compliance.

### A6 · Screen 6 — Success
- **Route:** `/onboarding/success` (ungated)
- **Status:** **Works** as a page

**Gap O-4 (MEDIUM):** the screen is reachable directly without any registration having occurred. Low user impact, but it means "success" is not evidence of a created account.

### A7 · Google OAuth callback
- **Route:** `/auth/google/callback` — added in `f409fea` to catch Google's redirect
- **Status:** page **Works**; flow **unvalidated**

Route exists and renders (it previously dead-ended at the consent screen). The exchange cannot run: it needs `GOOGLE_OAUTH_CLIENT_ID` / `SECRET` / `OAUTH_REDIRECT_BASE` **and** a live backend.

**Gap O-5 (BLOCKER, inherited):** blocked by O-1 and by missing OAuth credentials.

---

## Part B — Agency dashboard account entry

From `agency-dashboard/src/App.tsx`. All four screens are public; everything else sits behind `RequireAuth`.

| Screen | Route | Renders | Submits |
|---|---|---|---|
| Login | `/login` | pass | **Broken** |
| Sign-up | `/signup` | pass | unvalidated |
| Forgot password | `/forgot-password` | pass | unvalidated |
| Reset password | `/reset-password` | pass | unvalidated |

**Gap O-6 (BLOCKER) — agency login cannot reach an API.** `agency-dashboard/src/lib/api.ts` uses a **relative** `baseURL: '/api'`, while `vercel.json` rewrites `/(.*)` → `/index.html` with no `/api` exclusion. The login POST therefore lands on the dashboard's own static host:

```
POST https://agency-dashboard-git-klara-ai-….vercel.app/api/techscape/v1/auth/login
→ 405 Method Not Allowed
```

`405` is the static host refusing a POST — the request never reached FastAPI. No agency user can sign in, so **all 18 dashboard features are unreachable** (see `FEATURE_DASHBOARD.md`).

Sign-up, forgot-password and reset-password share the same client and the same defect; they were not separately exercised because the outcome is already determined.

---

## Onboarding gap register

| ID | Sev | Gap | Fix |
|---|---|---|---|
| O-1 | BLOCKER | `VITE_API_URL` → dead Railway host; customer login impossible | Repoint at the live API origin |
| O-6 | BLOCKER | Agency login POSTs to its own static host → 405 | Add `/api` rewrite, or use an absolute base |
| O-5 | BLOCKER | Google OAuth unrunnable | Fix O-1, then supply OAuth credentials |
| O-2 | HIGH | Plaintext password in localStorage | Drop `password` from persisted state; clear on success |
| O-3 | HIGH | OTP guard client-side only; no server check | Add a verification field to `RegisterBusinessIn`, enforce server-side |
| O-4 | MEDIUM | `/onboarding/success` reachable without registering | Gate on a real registration result |

### Not yet validated — needs a working backend

- Screens 3–5 field validation and persistence
- OTP delivery (Resend) and verification
- Consent capture reaching the backend (compliance-relevant)
- Account creation, duplicate-email handling, password policy enforcement server-side
- Agency sign-up / forgot / reset flows
- Google OAuth code exchange and session establishment
