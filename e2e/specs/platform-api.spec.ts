import { test, expect } from '@playwright/test'
import { record } from '../probe'
import { assertNotGated } from '../guard.spec-helper'

test.beforeAll(() => assertNotGated('platform'))

const SURFACE = 'Techscape AI platform (API)'

/** Endpoints that must answer for ANY downstream surface to work. */
const PUBLIC = [
  { feature: 'Health', path: '/api/health' },
  { feature: 'OpenAPI schema', path: '/openapi.json' },
  { feature: 'Swagger docs', path: '/docs' },
]

/** Auth entry points — unauthenticated calls should give 4xx/422, never 5xx. */
const AUTH = [
  { feature: 'Agency login', path: '/api/techscape/v1/auth/login', method: 'POST',
    body: { email: 'probe@example.com', password: 'wrong-password' } },
  { feature: 'Agency signup', path: '/api/techscape/v1/auth/register', method: 'POST',
    body: { email: 'probe@example.com', password: 'x' } },
  { feature: 'Google OAuth url', path: '/api/techscape/v1/auth/oauth/google/url', method: 'GET' },
  { feature: 'Traveller OTP request', path: '/api/travel/v1/me/auth/request-otp', method: 'POST',
    body: { email: 'probe@example.com' } },
  { feature: 'Traveller OTP verify', path: '/api/travel/v1/me/auth/verify-otp', method: 'POST',
    body: { email: 'probe@example.com', otp: '000000' } },
]

/** Protected endpoints — unauthenticated must be 401/403, never 200 and never 5xx. */
const PROTECTED = [
  { feature: 'Leads (journey board)', path: '/api/travel/v1/leads' },
  { feature: 'Bookings', path: '/api/travel/v1/bookings' },
  { feature: 'Packages', path: '/api/travel/v1/packages' },
  { feature: 'Payments', path: '/api/travel/v1/payments' },
  { feature: 'WhatsApp', path: '/api/travel/v1/whatsapp/sessions' },
  { feature: 'Follow-ups', path: '/api/travel/v1/followups' },
  { feature: 'Reports', path: '/api/travel/v1/reports' },
  { feature: 'Activity log', path: '/api/travel/v1/activity' },
  { feature: 'Usage / cost', path: '/api/travel/v1/usage' },
  { feature: 'AI config', path: '/api/travel/v1/ai-config' },
  { feature: 'Playbooks', path: '/api/travel/v1/playbooks' },
  { feature: 'Calls (live call)', path: '/api/travel/v1/calls' },
  { feature: 'Traveller trip', path: '/api/travel/v1/me/trip' },
  { feature: 'Businesses (empire)', path: '/api/techscape/v1/businesses' },
  { feature: 'Users / team', path: '/api/techscape/v1/users' },
]

test.describe('Platform API — reachability', () => {
  for (const ep of PUBLIC) {
    test(`public: ${ep.feature} ${ep.path}`, async ({ request }) => {
      const res = await request.get(ep.path, { failOnStatusCode: false })
      const status = res.status()
      const body = (await res.text()).slice(0, 200)
      if (status >= 500) {
        record({ surface: SURFACE, feature: ep.feature, route: ep.path, severity: 'BLOCKER',
          what: `Returns ${status} — serverless function fails to invoke`, evidence: body })
      } else if (status >= 400) {
        record({ surface: SURFACE, feature: ep.feature, route: ep.path, severity: 'HIGH',
          what: `Returns ${status}`, evidence: body })
      } else {
        record({ surface: SURFACE, feature: ep.feature, route: ep.path, severity: 'OK',
          what: `${status}`, evidence: body.slice(0, 120) })
      }
      expect(status, `${ep.path} -> ${body}`).toBeLessThan(500)
    })
  }
})

test.describe('Platform API — auth entry points', () => {
  for (const ep of AUTH) {
    test(`auth: ${ep.feature} ${ep.path}`, async ({ request }) => {
      const res = ep.method === 'POST'
        ? await request.post(ep.path, { data: ep.body ?? {}, failOnStatusCode: false })
        : await request.get(ep.path, { failOnStatusCode: false })
      const status = res.status()
      const body = (await res.text()).slice(0, 200)
      const sev = status >= 500 ? 'BLOCKER' : status === 404 ? 'HIGH' : 'OK'
      record({ surface: SURFACE, feature: ep.feature, route: ep.path, severity: sev as any,
        what: status >= 500 ? `${status} server error` : status === 404
          ? `404 — endpoint the frontend calls does not exist` : `${status} (expected rejection)`,
        evidence: body })
      expect(status, `${ep.path} -> ${body}`).toBeLessThan(500)
      expect(status, `${ep.path} missing -> ${body}`).not.toBe(404)
    })
  }
})

test.describe('Platform API — protected endpoints reject anonymous', () => {
  for (const ep of PROTECTED) {
    test(`protected: ${ep.feature} ${ep.path}`, async ({ request }) => {
      const res = await request.get(ep.path, { failOnStatusCode: false })
      const status = res.status()
      const body = (await res.text()).slice(0, 200)
      let sev: any = 'OK'; let what = `${status} — correctly rejects anonymous`
      if (status >= 500) { sev = 'BLOCKER'; what = `${status} server error` }
      else if (status === 200) { sev = 'BLOCKER'; what = '200 to an ANONYMOUS caller — data exposed without auth' }
      else if (status === 404) { sev = 'HIGH'; what = '404 — route not mounted' }
      record({ surface: SURFACE, feature: ep.feature, route: ep.path, severity: sev, what, evidence: body })
      expect(status, `${ep.path} -> ${body}`).toBeLessThan(500)
      expect([401, 403, 422], `${ep.path} -> ${status} ${body}`).toContain(status)
    })
  }
})
