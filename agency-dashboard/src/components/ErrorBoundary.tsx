/**
 * App-level React error boundary (Observability, PLATFORM_STATUS.md).
 *
 * window 'error' / 'unhandledrejection' listeners (lib/errorReporting.ts) do
 * NOT see React render errors — React catches those internally and, with no
 * boundary above the throw site, unmounts the entire tree, leaving a blank
 * page and an empty error queue. This boundary closes both gaps: the error is
 * reported through the same errorReporting stub (Sentry-shaped, so a future
 * DSN needs zero changes here) and the user gets a recovery path instead of a
 * white screen.
 *
 * Class component on purpose: componentDidCatch/getDerivedStateFromError have
 * no hook equivalent, and this stays dependency-free (no react-error-boundary
 * package — NO new packages is a hard constraint).
 *
 * Mounted in main.tsx around the router root — everything below the
 * QueryClientProvider is covered by one boundary. Screen-level boundaries can
 * nest inside later without changes here.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { reportError } from '../lib/errorReporting'

type Props = { children: ReactNode }
type State = { hasError: boolean }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    // componentStack pinpoints WHICH component threw — the message alone
    // rarely does for render errors.
    reportError(error, info.componentStack ?? undefined)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          style={{
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 12,
            padding: 24,
            textAlign: 'center',
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          <h1 style={{ fontSize: 20, margin: 0 }}>Something went wrong</h1>
          <p style={{ margin: 0, maxWidth: 420, color: '#666' }}>
            The error has been recorded. Reload to continue — if this keeps
            happening, tell the team what you were doing when it broke.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '8px 20px',
              borderRadius: 6,
              border: '1px solid #ccc',
              background: '#fff',
              cursor: 'pointer',
              fontSize: 14,
            }}
          >
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
