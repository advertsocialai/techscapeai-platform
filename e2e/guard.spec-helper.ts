import fs from 'fs'
import path from 'path'

/** Fails loudly rather than silently measuring Vercel's SSO login page. */
export function assertNotGated(target: string) {
  const p = path.join(__dirname, '.auth', 'status.json')
  if (!fs.existsSync(p)) return
  const status = JSON.parse(fs.readFileSync(p, 'utf8')) as Record<string, string>
  const s = status[target] || ''
  if (s.startsWith('STILL GATED')) {
    throw new Error(
      `[${target}] is behind Vercel SSO — every assertion below would test the ` +
      `Vercel login page instead of the app. Mint a fresh _vercel_share token. (${s})`)
  }
}
