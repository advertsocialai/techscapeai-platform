import { test, expect } from '@playwright/test'
import { record } from '../probe'
import { assertNotGated } from '../guard.spec-helper'

test.beforeAll(() => assertNotGated('klara'))

const SURFACE = 'Klara app — Onboarding'
const KEY = 'klara_onboarding_state'

test('onboarding does not persist the password in localStorage', async ({ page }) => {
  await page.goto('/onboarding/personal-info', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)

  // Complete step 1 properly so the context actually commits the value.
  const pw = 'Sup3rSecret-Probe!'
  await page.getByPlaceholder('John').fill('Probe')
  await page.getByPlaceholder('Smith').fill('Tester')
  await page.locator('input[type="email"]').first().fill('e2e-probe@example.com')
  await page.getByPlaceholder('9XX XXX XXXX').fill('9876543210')
  await page.getByPlaceholder('Create a strong password').fill(pw)
  await page.getByPlaceholder('Re-enter password').fill(pw)
  await page.getByRole('button', { name: /continue|next|proceed/i }).first()
    .click({ timeout: 10_000 }).catch(() => {})
  await page.waitForTimeout(3000)
  const raw = await page.evaluate((k) => localStorage.getItem(k), KEY)
  const leaked = !!raw && raw.includes(pw)

  record({
    surface: SURFACE, feature: 'Onboarding state persistence', route: '/onboarding/personal-info',
    severity: leaked ? 'HIGH' : 'OK',
    what: leaked
      ? `the plaintext password is written to localStorage["${KEY}"], readable by any script on the origin and left on shared machines after signup`
      : raw ? 'onboarding state persisted without the password' : 'no onboarding state persisted yet',
    evidence: raw ? String(raw).replace(new RegExp(pw, 'g'), '<THE-PASSWORD>').slice(0, 300) : '(null)',
  })
  expect(leaked, `password found in localStorage[${KEY}]`).toBeFalsy()
})

test('OTP step cannot be skipped by editing client state', async ({ page }) => {
  await page.goto('/onboarding/login', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1500)
  // Forge the exact state RequireStep reads.
  await page.evaluate((k) => {
    localStorage.setItem(k, JSON.stringify({
      email: 'forged@example.com', password: 'Forged-Passw0rd!', otpVerified: true,
    }))
  }, KEY)
  await page.goto('/onboarding/terms', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)

  const landed = new URL(page.url()).pathname
  const bypassed = landed === '/onboarding/terms'
  record({
    surface: SURFACE, feature: 'OTP verification guard', route: '/onboarding/terms',
    severity: bypassed ? 'HIGH' : 'OK',
    what: bypassed
      ? 'setting otpVerified=true in localStorage walks straight onto the terms step — email verification is enforced only in the client, and RegisterBusinessIn carries no OTP field for the server to check'
      : `client-forged state still redirected to ${landed}`,
    evidence: `landed=${landed}`,
  })
  expect(bypassed, 'client-side OTP guard was bypassed').toBeFalsy()
})
