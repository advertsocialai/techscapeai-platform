import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { authApi } from '../../lib/api'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const [devResetLink, setDevResetLink] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const res = await authApi.forgotPassword({ email })
      setSent(true)
      setDevResetLink(res.reset_token ? `/reset-password?token=${res.reset_token}` : null)
    } catch (err) {
      const message =
        (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ||
        'Something went wrong. Please try again.'
      setError(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 18, fontWeight: 700 }}>Reset your password</div>
          <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
            Enter your email and we&apos;ll send you a reset link
          </div>
        </div>
        {error && <div className="error-banner">{error}</div>}
        {sent ? (
          <div>
            <div
              style={{
                background: 'var(--green-dim)',
                border: '1px solid var(--green-border)',
                color: 'var(--green)',
                borderRadius: 8,
                padding: '10px 12px',
                fontSize: 12,
                marginBottom: 14,
              }}
            >
              If an account exists for {email}, we&apos;ve sent a password reset link.
            </div>
            {devResetLink && (
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 14 }}>
                Dev mode:{' '}
                <Link to={devResetLink} style={{ color: 'var(--green)' }}>
                  Open reset link
                </Link>
              </div>
            )}
          </div>
        ) : (
          <form onSubmit={onSubmit}>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <button
              className="btn primary"
              style={{ width: '100%', justifyContent: 'center', height: 40, marginBottom: 12 }}
              disabled={submitting}
            >
              {submitting ? 'Sending…' : 'Send reset link'}
            </button>
          </form>
        )}
        <div style={{ fontSize: 12, color: 'var(--text-dim)', textAlign: 'center' }}>
          <Link to="/login" style={{ color: 'var(--green)' }}>
            Back to sign in
          </Link>
        </div>
      </div>
    </div>
  )
}
