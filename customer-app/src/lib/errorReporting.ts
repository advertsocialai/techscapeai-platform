/**
 * Frontend error reporting — stub transport (Observability, PLATFORM_STATUS.md).
 *
 * Sentry-shaped so a real DSN (VITE_SENTRY_DSN) can go live later without
 * call-site changes. Without one, events are queued in memory (last 50) and
 * logged with an [error-reporting:stub] prefix — nothing leaves the browser,
 * and that is stated rather than implied. Wired in main.tsx so unhandled
 * errors and promise rejections are captured app-wide.
 */
type Ev = { kind: string; message: string; at: string }
const queue: Ev[] = []

function record(kind: string, message: string) {
  const ev = { kind, message: message.slice(0, 500), at: new Date().toISOString() }
  queue.push(ev)
  if (queue.length > 50) queue.shift()
  // eslint-disable-next-line no-console
  console.error(`[error-reporting:stub] ${kind}:`, ev.message)
}

export function initErrorReporting() {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (dsn) {
    // Live mode is a deliberate follow-up: @sentry/browser is not a dependency
    // until a DSN exists (BLK-6). Loudly say the DSN is being ignored so it is
    // never silently dropped.
    console.warn('[error-reporting] VITE_SENTRY_DSN set but @sentry/browser not installed — stub active (BLK-6)')
  }
  window.addEventListener('error', (e) => record('error', e.message))
  window.addEventListener('unhandledrejection', (e) =>
    record('unhandledrejection', String((e as PromiseRejectionEvent).reason)))
}

/**
 * Report an error that was CAUGHT (React ErrorBoundary, explicit catch sites)
 * rather than escaping to window. Same stub transport, same queue — so a
 * future DSN picks these up with zero call-site changes.
 */
export function reportError(error: unknown, context?: string) {
  const msg = error instanceof Error ? `${error.name}: ${error.message}` : String(error)
  record('boundary', context ? `${msg} | ${context.slice(0, 300)}` : msg)
}

export function reportedEvents(): readonly Ev[] {
  return queue
}
