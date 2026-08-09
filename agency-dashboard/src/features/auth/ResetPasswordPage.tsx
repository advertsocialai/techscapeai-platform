import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { authApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { isPasswordValid, passwordErrors } from '../../lib/passwordValidation'
import PasswordRequirements from './PasswordRequirements'

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (!isPasswordValid(password)) {
      setError(`Password must contain ${passwordErrors(password).join(', ').toLowerCase()}`)
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setSubmitting(true)
    try {
      await authApi.resetPassword({ token, new_password: password })
      setDone(true)
      setTimeout(() => navigate('/login', { replace: true }), 1500)
    } catch (err) {
      // This endpoint runs the same password-strength validator as register, so
      // a 422 with an ARRAY `detail` is a live possibility here — exactly the
      // shape the old `detail as string` cast rendered and crashed on.
      setError(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (!token) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="error-banner">This reset link is missing or invalid.</div>
          <div style={{ fontSize: 12, color: 'var(--text-dim)', textAlign: 'center' }}>
            <Link to="/forgot-password" style={{ color: 'var(--green)' }}>
              Request a new link
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 18, fontWeight: 700 }}>Set a new password</div>
          <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>Choose a new password for your account</div>
        </div>
        {error && <div className="error-banner">{error}</div>}
        {done ? (
          <div
            style={{
              background: 'var(--green-dim)',
              border: '1px solid var(--green-border)',
              color: 'var(--green)',
              borderRadius: 8,
              padding: '10px 12px',
              fontSize: 12,
            }}
          >
            Password updated. Redirecting to sign in…
          </div>
        ) : (
          <form onSubmit={onSubmit}>
            <div className="field">
              <label htmlFor="password">New password</label>
              <input
                id="password"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <PasswordRequirements password={password} />
            <div className="field">
              <label htmlFor="confirmPassword">Confirm new password</label>
              <input
                id="confirmPassword"
                type="password"
                required
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>
            <button
              className="btn primary"
              style={{ width: '100%', justifyContent: 'center', height: 40, marginBottom: 12 }}
              disabled={submitting}
            >
              {submitting ? 'Updating…' : 'Update password'}
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
