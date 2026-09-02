import { type Page, type Request, type Response } from '@playwright/test'
import fs from 'fs'
import path from 'path'

export type Finding = {
  surface: string
  feature: string
  route: string
  severity: 'BLOCKER' | 'HIGH' | 'MEDIUM' | 'LOW' | 'OK'
  what: string
  evidence?: string
}

const OUT = path.join(__dirname, 'artifacts', 'findings.jsonl')

export function record(f: Finding) {
  fs.mkdirSync(path.dirname(OUT), { recursive: true })
  fs.appendFileSync(OUT, JSON.stringify(f) + '\n')
}

/** Attaches console/network collectors. Returns a snapshot accessor. */
export function instrument(page: Page) {
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  const failedRequests: string[] = []
  const apiCalls: { url: string; status: number; ct: string; bodyStart?: string }[] = []

  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 400))
  })
  page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 400)))
  page.on('requestfailed', (r: Request) =>
    failedRequests.push(`${r.method()} ${r.url()} :: ${r.failure()?.errorText}`))
  page.on('response', async (r: Response) => {
    const u = r.url()
    // A document navigation is not an API call — only count XHR/fetch.
    const rt = r.request().resourceType()
    if (rt !== 'xhr' && rt !== 'fetch') return
    if (!/[/]api[/]|[/]health|openapi|[/]auth|otp/.test(u)) return
    const ct = r.headers()['content-type'] || ''
    let bodyStart: string | undefined
    try { bodyStart = (await r.text()).slice(0, 160) } catch { /* body consumed */ }
    apiCalls.push({ url: u, status: r.status(), ct, bodyStart })
  })

  return () => ({ consoleErrors, pageErrors, failedRequests, apiCalls })
}

/** Navigate a route and report how it actually behaves live. */
export async function auditRoute(
  page: import('@playwright/test').Page,
  opts: { surface: string; feature: string; route: string; expectText?: RegExp }
) {
  const snap = instrument(page)
  let navError = ''
  try {
    await page.goto(opts.route, { waitUntil: 'domcontentloaded', timeout: 60_000 })
    await page.waitForTimeout(3500)
  } catch (e) {
    navError = (e as Error).message
  }
  const s = snap()
  const bodyText = (await page.locator('body').innerText().catch(() => '')) || ''
  const landedOn = new URL(page.url()).pathname

  // API calls that returned HTML instead of JSON = the SPA rewrite swallowed them.
  const htmlForApi = s.apiCalls.filter(
    (c) => /\/api\//.test(c.url) && /text\/html/.test(c.ct)
  )
  const serverErrors = s.apiCalls.filter((c) => c.status >= 500)
  const authErrors = s.apiCalls.filter((c) => c.status === 401 || c.status === 403)
  const notFound = s.apiCalls.filter((c) => c.status === 404)

  let severity: Finding['severity'] = 'OK'
  const problems: string[] = []

  if (navError) { severity = 'BLOCKER'; problems.push(`navigation failed: ${navError}`) }
  if (bodyText.trim().length < 20) { severity = 'BLOCKER'; problems.push('renders blank (no visible text)') }
  if (s.pageErrors.length) { severity = 'BLOCKER'; problems.push(`uncaught JS: ${s.pageErrors[0]}`) }
  if (htmlForApi.length) {
    severity = severity === 'OK' ? 'BLOCKER' : severity
    problems.push(`${htmlForApi.length} /api call(s) returned text/html — SPA catch-all rewrite swallows the API path, no backend is reachable`)
  }
  if (serverErrors.length) {
    severity = severity === 'OK' ? 'BLOCKER' : severity
    problems.push(`${serverErrors.length} API call(s) 5xx: ${serverErrors[0].url} -> ${serverErrors[0].status}`)
  }
  if (notFound.length) {
    severity = severity === 'OK' ? 'HIGH' : severity
    problems.push(`${notFound.length} API call(s) 404: ${notFound[0].url}`)
  }
  const redirected = landedOn !== opts.route.split('?')[0]
  if (opts.expectText && !redirected && !opts.expectText.test(bodyText)) {
    severity = severity === 'OK' ? 'HIGH' : severity
    problems.push(`expected content ${opts.expectText} not found`)
  }
  if (redirected) {
    problems.push(`route guard redirected ${opts.route} -> ${landedOn}`)
  }
  if (severity === 'OK' && authErrors.length) {
    problems.push(`${authErrors.length} API call(s) 401/403 (expected when signed out)`)
  }
  if (s.consoleErrors.length && severity === 'OK') {
    severity = 'MEDIUM'
    problems.push(`console errors: ${s.consoleErrors[0]}`)
  }

  record({
    surface: opts.surface,
    feature: opts.feature,
    route: opts.route,
    severity,
    what: problems.length ? problems.join(' | ') : 'renders and behaves as expected',
    evidence: `landed=${landedOn} | text="${bodyText.replace(/\s+/g, ' ').slice(0, 220)}" | apiCalls=${JSON.stringify(s.apiCalls.slice(0, 4))}`,
  })

  return { snap: s, bodyText, landedOn, severity, problems }
}
