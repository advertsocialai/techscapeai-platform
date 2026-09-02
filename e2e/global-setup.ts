import { chromium, type FullConfig } from '@playwright/test'
import { TARGETS, type TargetKey } from './urls'
import fs from 'fs'
import path from 'path'

const AUTH_DIR = path.join(__dirname, '.auth')

/** True when the page is showing the real deployment, not Vercel's SSO wall. */
function onDeployment(url: string) {
  return !/(^https:\/\/vercel\.com)/.test(url)
}

/**
 * Vercel _vercel_share tokens are single-use: every run would otherwise burn
 * them. So we first try the cookie we already persisted, and only spend a
 * token when that cookie is genuinely gone. Fresh tokens are supplied via
 * .auth/tokens.json (written by the operator/MCP) or the *_SHARE env vars.
 */
export default async function globalSetup(_config: FullConfig) {
  fs.mkdirSync(AUTH_DIR, { recursive: true })

  const tokenFile = path.join(AUTH_DIR, 'tokens.json')
  const fresh: Record<string, string> = fs.existsSync(tokenFile)
    ? JSON.parse(fs.readFileSync(tokenFile, 'utf8'))
    : {}

  const browser = await chromium.launch()
  const status: Record<string, string> = {}

  const only = process.env.E2E_ONLY
  const keys = (Object.keys(TARGETS) as TargetKey[]).filter(k => !only || k === only)
  for (const key of keys) {
    const t = TARGETS[key]
    const statePath = path.join(AUTH_DIR, `${key}.json`)

    // 1. Try the cookie we already have.
    if (fs.existsSync(statePath)) {
      const ctx = await browser.newContext({ storageState: statePath })
      const page = await ctx.newPage()
      try {
        await page.goto(t.base + '/', { waitUntil: 'domcontentloaded', timeout: 45_000 })
        await page.waitForTimeout(1500)
      } catch { /* fall through to token exchange */ }
      if (onDeployment(page.url())) {
        status[key] = `REUSED COOKIE -> ${page.url()}`
        await ctx.storageState({ path: statePath })
        await ctx.close()
        continue
      }
      await ctx.close()
    }

    // 2. Spend a share token.
    const token = fresh[key] || t.share
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    try {
      await page.goto(`${t.base}/?_vercel_share=${token}`, { waitUntil: 'networkidle', timeout: 90_000 })
      await page.waitForTimeout(3000)
    } catch (e) {
      status[key] = `NAV ERROR ${(e as Error).message}`
    }
    status[key] = onDeployment(page.url())
      ? `TOKEN EXCHANGED -> ${page.url()}`
      : `STILL GATED (token spent or invalid) -> ${page.url().slice(0, 90)}`
    await ctx.storageState({ path: statePath })
    await ctx.close()
  }
  await browser.close()

  fs.writeFileSync(path.join(AUTH_DIR, 'status.json'), JSON.stringify(status, null, 2))
  for (const [k, v] of Object.entries(status)) console.log(`[global-setup] ${k}: ${v}`)

  const gated = Object.entries(status).filter(([, v]) => v.startsWith('STILL GATED'))
  if (gated.length) {
    console.error(`\n[global-setup] ${gated.length} target(s) still behind Vercel SSO — ` +
      `their results would measure the Vercel login page, not the app. ` +
      `Mint fresh tokens into e2e/.auth/tokens.json before trusting those rows.\n`)
  }
}
