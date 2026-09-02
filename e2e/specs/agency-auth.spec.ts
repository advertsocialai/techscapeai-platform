import { test, expect } from '@playwright/test'
import { auditRoute, instrument, record } from '../probe'
import { assertNotGated } from '../guard.spec-helper'

test.beforeAll(() => assertNotGated('agency'))

const SURFACE = 'Agency dashboard — Auth & onboarding'

const SCREENS = [
  { feature: 'Login',            route: '/login',           expectText: /email|password|sign in|log in/i },
  { feature: 'Sign-up',          route: '/signup',          expectText: /email|password|sign ?up|create/i },
  { feature: 'Forgot password',  route: '/forgot-password', expectText: /email|reset|forgot/i },
  { feature: 'Reset password',   route: '/reset-password',  expectText: /password|reset/i },
]

test.describe('Agency auth screens', () => {
  for (const s of SCREENS) {
    test(`${s.feature} (${s.route})`, async ({ page }) => {
      const r = await auditRoute(page, { surface: SURFACE, ...s })
      expect(r.severity, `${s.route}: ${r.problems.join(' | ')}`).not.toBe('BLOCKER')
    })
  }

  test('agency login submits to a reachable backend', async ({ page }) => {
    const snap = instrument(page)
    await page.goto('/login', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    const email = page.locator('input[type="email"], input[name="email"]').first()
    const pw = page.locator('input[type="password"]').first()
    if (!(await email.count()) || !(await pw.count())) {
      record({ surface: SURFACE, feature: 'Login submit', route: '/login',
        severity: 'BLOCKER', what: 'email/password inputs not found' })
      expect(false, 'login inputs missing').toBeTruthy(); return
    }
    await email.fill('e2e-probe@example.com')
    await pw.fill('Probe-Passw0rd!')
    await page.getByRole('button', { name: /sign in|log ?in|continue/i }).first()
      .click({ timeout: 10_000 }).catch(() => {})
    await page.waitForTimeout(5000)
    const s = snap()
    const auth = s.apiCalls.filter((c) => /auth|login/.test(c.url))
    let severity: any = 'OK'
    let what = `login POST -> ${auth.map(c => c.status).join(',')}`
    if (!auth.length) { severity = 'BLOCKER'; what = 'Sign in fired no auth request — form not wired' }
    else if (auth.some(c => /text\/html/.test(c.ct))) {
      severity = 'BLOCKER'
      what = 'login POST returned text/html — vercel.json rewrites /(.*) to index.html, so /api never reaches a backend on this deployment'
    } else if (auth.some(c => c.status >= 400 && ![401, 403, 422].includes(c.status))) {
      const b = auth.find(c => c.status >= 400 && ![401, 403, 422].includes(c.status))!
      severity = 'BLOCKER'
      what = `login POST ${b.url} returned ${b.status} — the request went to the dashboard's own static host, not to an API. ` +
        `agency-dashboard/src/lib/api.ts uses a relative baseURL of '/api', and vercel.json rewrites /(.*) to /index.html, ` +
        `so no agency user can sign in on this deployment.`
    }
    record({ surface: SURFACE, feature: 'Login submit', route: '/login', severity, what,
      evidence: JSON.stringify(s.apiCalls.slice(0, 5)) })
    expect(severity, what).not.toBe('BLOCKER')
  })
})
