# Klara-ai live E2E suite

Playwright suite that validates the three live surfaces of the `Klara-ai` branch against their real Vercel deployments.

Findings: [`docs/e2e-validation/`](../docs/e2e-validation/)

## Install

```bash
cd e2e
npm install
npx playwright install chromium
```

## The Vercel SSO constraint — read this before running

All three previews are behind Vercel Deployment Protection. Two behaviours will silently corrupt results:

1. **A gated request still returns `200`** — it is Vercel's login page, not the app. An early run of this suite "passed" 15 checks that were measuring `vercel.com/login`.
2. **Only the most recently minted `_vercel_share` token is valid.** Minting one for surface B revokes surface A's, *including the cookie already exchanged for it*.

So: **validate one surface at a time**, minting its token immediately before the run.

`global-setup.ts` records the outcome in `.auth/status.json`, and every spec calls `assertNotGated()` in `beforeAll` — a gated surface fails loudly rather than reporting false green.

## Running

Mint a share link for the surface (Vercel MCP `get_access_to_vercel_url`, or the Vercel dashboard), then:

```bash
# 1. Klara app
echo '{"klara":"<TOKEN>"}' > .auth/tokens.json
rm -f .auth/klara.json
E2E_ONLY=klara npx playwright test --project=klara

# 2. Agency dashboard
echo '{"agency":"<TOKEN>"}' > .auth/tokens.json
rm -f .auth/agency.json
E2E_ONLY=agency npx playwright test --project=agency

# 3. Platform API
echo '{"platform":"<TOKEN>"}' > .auth/tokens.json
rm -f .auth/platform.json
E2E_ONLY=platform npx playwright test --project=platform
```

`E2E_ONLY` limits global setup to one target so it does not waste (or clobber) the others' state.

Once deployment protection is lifted, or a bypass-for-automation secret is configured, all three can run in one pass: `npx playwright test`.

## Output

| Path | Contents |
|---|---|
| `artifacts/findings.jsonl` | one JSON finding per check, with severity and evidence |
| `artifacts/findings-{klara,agency,platform}.jsonl` | per-surface snapshots |
| `artifacts/html/` | Playwright HTML report |
| `test-results/` | screenshots and traces for failures |

Consolidate and summarise:

```bash
cat artifacts/findings-*.jsonl > artifacts/findings-all.jsonl
node -e "const r=require('fs').readFileSync('artifacts/findings-all.jsonl','utf8').trim().split('\n').map(JSON.parse);const c={};r.forEach(x=>c[x.severity]=(c[x.severity]||0)+1);console.log(c);r.filter(x=>x.severity!=='OK').forEach(x=>console.log('['+x.severity+'] '+x.surface+' :: '+x.feature+' — '+x.what))"
```

## Layout

| File | Purpose |
|---|---|
| `urls.ts` | the three live targets and their fallback tokens |
| `global-setup.ts` | SSO bypass: reuse cookie, else spend a token; writes `.auth/status.json` |
| `guard.spec-helper.ts` | `assertNotGated()` — prevents false green on a gated surface |
| `probe.ts` | console/network instrumentation, `auditRoute()`, findings recorder |
| `specs/platform-api.spec.ts` | 23 endpoints: reachability, auth entry points, anonymous rejection |
| `specs/klara-onboarding.spec.ts` | onboarding screens 1–6, step guards, login submit |
| `specs/klara-trip.spec.ts` | traveller dashboard, traveller guard, OTP wiring |
| `specs/klara-security.spec.ts` | localStorage password persistence, OTP guard bypass |
| `specs/agency-auth.spec.ts` | login/signup/forgot/reset, login submit |
| `specs/agency-dashboard.spec.ts` | all 18 feature routes and their auth guards |

## Notes on probe accuracy

Two corrections were needed during the run; both are worth preserving.

- **Document navigations are not API calls.** The instrumentation filters to `xhr`/`fetch` only. Without it, a page load at `/trip/login` was mis-reported as an OTP endpoint returning HTML.
- **A guarded redirect is correct behaviour.** `auditRoute()` skips the content assertion when the route redirected, so `RequireStep` sending `/onboarding/terms` → `/onboarding/personal-info` is recorded as a working guard, not missing content.

Vercel preview-toolbar requests (`vercel.live`, `vercel.com`) are excluded from application-traffic assertions.
