import { test, expect } from '@playwright/test'
import { auditRoute, record } from '../probe'
import { assertNotGated } from '../guard.spec-helper'

test.beforeAll(() => assertNotGated('klara'))

const SURFACE = 'Klara app — Traveller dashboard'

const SCREENS = [
  { feature: 'Traveller sign-in (email → OTP)', route: '/trip/login', expectText: /email|otp|sign in|continue/i },
  { feature: 'Trip overview',                   route: '/trip' },
  { feature: 'Payments',                        route: '/trip/payments' },
  { feature: 'Messages',                        route: '/trip/messages' },
  { feature: '/dashboard alias → /trip',        route: '/dashboard' },
]

test.describe('Klara traveller dashboard', () => {
  for (const s of SCREENS) {
    test(`${s.feature} (${s.route})`, async ({ page }) => {
      const r = await auditRoute(page, { surface: SURFACE, ...s })
      expect(r.severity, `${s.route}: ${r.problems.join(' | ')}`).not.toBe('BLOCKER')
    })
  }

  test('signed-out traveller cannot reach trip data', async ({ page }) => {
    await page.goto('/trip', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)
    const landed = new URL(page.url()).pathname
    const guarded = landed.includes('login')
    record({
      surface: SURFACE, feature: 'RequireTraveller guard', route: '/trip',
      severity: guarded ? 'OK' : 'HIGH',
      what: guarded ? `guard redirects anonymous to ${landed}`
                    : `anonymous visitor stays on ${landed} — traveller guard did not redirect`,
      evidence: `landed=${landed}`,
    })
    expect(guarded, `anonymous landed on ${landed}`).toBeTruthy()
  })

  test('traveller OTP request is wired to a real endpoint', async ({ page }) => {
    const calls: { url: string; status: number; ct: string }[] = []
    const consoleErrors: string[] = []
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 300)) })
    page.on('response', (r) => {
      const rt = r.request().resourceType()
      if (rt !== 'xhr' && rt !== 'fetch') return          // a page navigation is not an API call
      if (/vercel.live|vercel.com/.test(r.url())) return // Vercel preview toolbar, not our app
      if (/auth|otp|login/.test(r.url()))
        calls.push({ url: r.url(), status: r.status(), ct: r.headers()['content-type'] || '' })
    })
    await page.goto('/trip/login', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    const email = page.locator('input[type="email"], input[type="text"]').first()
    if (await email.count()) {
      await email.fill('e2e-probe@example.com')
      await page.getByRole('button', { name: /send|otp|continue|next|sign in/i }).first()
        .click({ timeout: 10_000 }).catch(() => {})
      await page.waitForTimeout(5000)
    }
    // 401/403/422 are legitimate rejections of a probe address. Anything else
    // (404/405/5xx/HTML) means the request never reached the traveller API.
    const bad = calls.filter((c) =>
      c.status >= 500 || /text[/]html/.test(c.ct) ||
      (c.status >= 400 && ![401, 403, 422].includes(c.status)))
    let severity: any = 'OK'
    let what = `OTP request produced ${calls.length} call(s): ${calls.map(c => `${c.status}`).join(',')}`
    if (!calls.length) { severity = 'BLOCKER'; what = `requesting an OTP produced no XHR to any auth endpoint. Console: ${consoleErrors.slice(0, 2).join(' || ') || '(none)'}` }
    else if (bad.length) { severity = 'BLOCKER'; what = `OTP endpoint ${bad[0].url} returned ${bad[0].status}${bad[0].ct ? ' / ' + bad[0].ct : ''} — traveller login cannot complete` }
    record({ surface: SURFACE, feature: 'Traveller OTP request', route: '/trip/login',
      severity, what, evidence: `calls=${JSON.stringify(calls.slice(0, 5))} consoleErr=${JSON.stringify(consoleErrors.slice(0, 2))}` })
    expect(severity, what).not.toBe('BLOCKER')
  })
})
