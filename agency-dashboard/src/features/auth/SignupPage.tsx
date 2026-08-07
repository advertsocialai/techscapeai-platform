import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth'
import { isPasswordValid, passwordErrors } from '../../lib/passwordValidation'
import PasswordRequirements from './PasswordRequirements'

export default function SignupPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [businessName, setBusinessName] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

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
      await register({
        business_name: businessName,
        contact_email: email,
        user_first_name: firstName || undefined,
        user_last_name: lastName || undefined,
        user_password: password,
        industry: 'travel',
      })
      navigate('/', { replace: true })
    } catch (err) {
      if (err instanceof Error && err.message === 'ACCOUNT_CREATED_LOGIN_FAILED') {
        setError('Your account was created, but we could not sign you in automatically. Please sign in below.')
      } else {
        const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
        setError(typeof detail === 'string' ? detail : 'Could not create your account. Please check your details and try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card" style={{ width: 400 }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 18, fontWeight: 700 }}>Create your agency</div>
          <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>Set up GoGaga Agency Dashboard access</div>
        </div>
        {error && <div className="error-banner">{error}</div>}
        <form onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="businessName">Agency / business name</label>
            <input
              id="businessName"
              required
              value={businessName}
              onChange={(e) => setBusinessName(e.target.value)}
            />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div className="field">
              <label htmlFor="firstName">First name</label>
              <input id="firstName" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="lastName">Last name</label>
              <input id="lastName" value={lastName} onChange={(e) => setLastName(e.target.value)} />
            </div>
          </div>
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
          <div className="field">
            <label htmlFor="password">Password</label>
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
            <label htmlFor="confirmPassword">Confirm password</label>
            <input
              id="confirmPassword"
              type="password"
              required
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </div>
          <button className="btn primary" style={{ width: '100%', justifyContent: 'center', height: 40, marginBottom: 12 }} disabled={submitting}>
            {submitting ? 'Creating account…' : 'Create account'}
          </button>
        </form>
        <div style={{ fontSize: 12, color: 'var(--text-dim)', textAlign: 'center' }}>
          Already have an account? <Link to="/login" style={{ color: 'var(--green)' }}>Sign in</Link>
        </div>
      </div>
    </div>
  )
}
