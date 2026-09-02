import { test, expect } from '@playwright/test'
import { auditRoute, instrument, record } from '../probe'
import { assertNotGated } from '../guard.spec-helper'

test.beforeAll(() => assertNotGated('klara'))

const SURFACE = 'Klara app — Onboarding'

/** Screens 1–6 of the customer onboarding funnel, plus the OAuth landing. */
const SCREENS = [
  { feature: 'S1 Login / Sign-up',      route: '/onboarding/login',         expectText: /email|sign in|password/i },
  { feature: 'S2 Personal info',        route: '/onboarding/personal-info', expectText: /name|phone|personal/i },
  { feature: 'S3 Address',              route: '/onboarding/address',       expectText: /address|city|pin/i },
  { feature: 'S4 OTP verification',     route: '/onboarding/otp',           expectText: /otp|verif|code/i },
  { feature: 'S5 Terms & conditions',   route: '/onboarding/terms',         expectText: /terms|accept|agree/i },
  { feature: 'S6 Success',              route: '/onboarding/success',       expectText: /success|welcome|done|thank/i },
  { feature: 'Google OAuth callback',   route: '/auth/google/callback',     expectText: /./ },
]

test.describe('Klara onboarding — every screen renders', () => {
  for (const s of SCREENS) {
    test(`${s.feature} (${s.route})`, async ({ page }) => {
      const r = await auditRoute(page, { surface: SURFACE, ...s })
      expect(r.severity, `${s.route}: ${r.problems.join(' | ')}`).not.toBe('BLOCKER')
    })
  }
})

test.describe('Klara onboarding — step guard behaviour', () => {
  test('deep-linking a later step redirects back to the funnel start', async ({ page }) => {
    await page.goto('/onboarding/terms', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    const landed = new URL(page.url()).pathname
    const guarded = landed !== '/onboarding/terms'
    record({
      surface: SURFACE, feature: 'RequireStep guard', route: '/onboarding/terms',
      severity: guarded ? 'OK' : 'HIGH',
      what: guarded
        ? `guard active — redirected to ${landed}`
        : 'NO GUARD — a cold deep-link reaches the terms step without completing personal-info/address/OTP',
      evidence: `landed=${landed}`,
    })
    expect(guarded, `deep-link landed on ${landed} with no guard`).toBeTruthy()
  })

  test('root redirects into the onboarding funnel', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    const landed = new URL(page.url()).pathname
    record({
      surface: SURFACE, feature: 'Root redirect', route: '/',
      severity: landed.startsWith('/onboarding') ? 'OK' : 'HIGH',
      what: `/ lands on ${landed}`, evidence: landed,
    })
    expect(landed).toContain('/onboarding')
  })
})

test.describe('Klara onboarding — login form actually submits', () => {
  test('submitting credentials reaches a backend (not the SPA rewrite)', async ({ page }) => {
    const snap = instrument(page)
    await page.goto('/onboarding/login', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)

    const email = page.locator('input[type="email"]').first()
    const pw = page.locator('input[type="password"]').first()

    if (!(await email.count()) || !(await pw.count())) {
      record({ surface: SURFACE, feature: 'Login submit', route: '/onboarding/login',
        severity: 'BLOCKER', what: 'email/password inputs not found on the login screen' })
      test.fail(true, 'login inputs missing'); return
    }

    await email.fill('e2e-probe@example.com')
    await pw.fill('Probe-Passw0rd!')
    const btn = page.getByRole('button', { name: /sign in|log ?in|continue/i }).first()
    const btnCount = await btn.count()
    const disabled = btnCount ? await btn.isDisabled().catch(() => null) : null
    await btn.click({ timeout: 10_000 }).catch(() => {})
    await page.waitForTimeout(6000)
    const afterUrl = new URL(page.url()).pathname
    const visible = (await page.locator('body').innerText().catch(() => '')).replace(/s+/g, ' ').slice(0, 300)
    const s = snap()
    const authCalls = s.apiCalls.filter((c) => /auth|login/.test(c.url))
    const htmlBack = authCalls.filter((c) => /text\/html/.test(c.ct))
    const server5xx = authCalls.filter((c) => c.status >= 500)

    let severity: any = 'OK'
    let what = `login POST reached the API (${authCalls.map(c => c.status).join(',')})`
    if (!authCalls.length) {
      severity = 'BLOCKER'
      what = `clicking Sign in fired NO XHR to any auth endpoint (button found=${btnCount}, disabled=${disabled}, url after=${afterUrl}) — either client-side validation blocked submit, or the submit handler is not wired`
    } else if (htmlBack.length) {
      severity = 'BLOCKER'
      what = `login POST returned text/html — the SPA catch-all rewrite intercepts /api, so login can never succeed on this deployment`
    } else if (server5xx.length) {
      severity = 'BLOCKER'
      what = `login POST returned ${server5xx[0].status} from the API`
    }
    record({ surface: SURFACE, feature: 'Login submit', route: '/onboarding/login',
      severity, what, evidence: `btn=${btnCount} disabled=${disabled} after=${afterUrl} screen="${visible}" calls=${JSON.stringify(s.apiCalls.slice(0, 5))} consoleErr=${JSON.stringify(s.consoleErrors.slice(0, 2))}` })
    expect(severity, what).not.toBe('BLOCKER')
  })
})
