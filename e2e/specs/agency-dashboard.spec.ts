import { test, expect } from '@playwright/test'
import { auditRoute, record } from '../probe'
import { assertNotGated } from '../guard.spec-helper'

test.beforeAll(() => assertNotGated('agency'))

const SURFACE = 'Agency dashboard — Features'

/** Every authenticated feature route behind RequireAuth. */
const FEATURES = [
  { feature: 'Mission Control (home)',   route: '/' },
  { feature: 'Journey Board',            route: '/journey-board' },
  { feature: 'Guest Story (lead detail)',route: '/journey-board/1' },
  { feature: 'Bookings',                 route: '/bookings' },
  { feature: 'Packages',                 route: '/packages' },
  { feature: 'Payment Links',            route: '/payment-links' },
  { feature: 'WhatsApp',                 route: '/whatsapp' },
  { feature: 'Follow-ups',               route: '/follow-ups' },
  { feature: 'Reports',                  route: '/reports' },
  { feature: 'Cost',                     route: '/cost' },
  { feature: 'Report Schedules',         route: '/report-schedules' },
  { feature: 'Team',                     route: '/team' },
  { feature: 'Activity Log',             route: '/activity' },
  { feature: 'Playbooks',                route: '/playbooks' },
  { feature: 'AI Config',                route: '/ai-config' },
  { feature: 'Empire (admin)',           route: '/empire' },
  { feature: 'Live Call list',           route: '/live-call' },
  { feature: 'Live Call detail',         route: '/live-call/1' },
]

test.describe('Agency dashboard feature routes', () => {
  for (const f of FEATURES) {
    test(`${f.feature} (${f.route})`, async ({ page }) => {
      const r = await auditRoute(page, { surface: SURFACE, ...f })
      // Signed out, RequireAuth should send us to /login rather than render a broken page.
      const redirectedToLogin = r.landedOn.includes('login')
      record({
        surface: SURFACE, feature: `${f.feature} — auth guard`, route: f.route,
        severity: redirectedToLogin ? 'OK' : 'HIGH',
        what: redirectedToLogin
          ? 'RequireAuth redirects anonymous to /login'
          : `anonymous visitor stayed on ${r.landedOn} — feature route not guarded`,
        evidence: `landed=${r.landedOn}`,
      })
      expect(r.severity, `${f.route}: ${r.problems.join(' | ')}`).not.toBe('BLOCKER')
    })
  }
})
