import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api, { authApi } from '../../../lib/api'
import { errorMessage } from '../../../lib/errors'

// ── Klara Logo ──────────────────────────────────────
function KlaraLogo() {
  return (
    <div style={{
      width: 68, height: 68, borderRadius: 22,
      background: 'rgba(255,255,255,0.07)',
      border: '1.5px solid rgba(255,255,255,0.12)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08), 0 0 40px rgba(59,143,232,0.12)',
    }}>
      <svg width="38" height="30" viewBox="0 0 167 134" fill="none">
        <path d="M166 32C166 49 152 63 134 63C117 63 103 49 103 32C103 14 117 0 134 0C152 0 166 14 166 32Z" fill="#2D7DD2"/>
        <path d="M134 70C152 70 166 85 166 102C166 119 153 133 136 134H70C65 134 62 128 66 124L112 80C117 74 126 70 134 70Z" fill="rgba(255,255,255,0.95)"/>
        <path d="M0 102C0 85 14 70 32 70C49 70 63 85 63 102C63 120 49 134 32 134C14 134 0 120 0 102Z" fill="#F7A97C"/>
        <path d="M32 63C14 63 0 49 0 32C0 15 13 1 30 0H96C101 0 104 6 100 10L55 54C49 60 41 63 32 63Z" fill="rgba(255,255,255,0.95)"/>
      </svg>
    </div>
  )
}

// ── Eye Icon ─────────────────────────────────────────
function EyeIcon({ open }: { open: boolean }) {
  return open ? (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  ) : (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  )
}

export default function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function handleLogin() {
    if (!email || !password) {
      setError('Please enter your email and password')
      return
    }
    setError('')
    setLoading(true)
    try {
      const res = await authApi.login({ email, password })
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('refresh_token', res.data.refresh_token)
      navigate('/dashboard')
    } catch (err) {
      // Was: `detail || 'Invalid email or password'`, which reported a network
      // outage or a 500 as bad credentials — sending the user to reset a
      // password that was never wrong. errorMessage() distinguishes them.
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  // Was a dead <span> with no onClick, while authApi.forgotPassword() sat
  // defined and never called. A control that looks clickable and does nothing
  // is worse than no control: the user concludes the product is broken.
  async function handleForgot() {
    if (!email) {
      setError('Enter your email first, then tap Forgot password')
      return
    }
    setError('')
    setLoading(true)
    try {
      await authApi.forgotPassword(email)
      // Deliberately does not confirm whether the address exists — same
      // enumeration guard the backend applies.
      setError('')
      setNotice('If that email has an account, a reset link is on its way.')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  // GET /auth/oauth/google/url returns the provider URL to hand the browser.
  // A full-page redirect, not an XHR: an OAuth consent screen cannot complete
  // inside a fetch, and the callback has to land on a real navigation.
  async function handleGoogle() {
    setError('')
    setLoading(true)
    try {
      const res = await api.get<{ url?: string; authorization_url?: string }>(
        '/auth/oauth/google/url',
      )
      const url = res.data?.url || res.data?.authorization_url
      if (!url) throw new Error('Google sign-in is not configured on the server yet.')
      window.location.href = url
    } catch (err) {
      setError(errorMessage(err))
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleLogin()
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px 20px',
    }}>
      {/* Ambient glows */}
      <div style={{ position: 'fixed', top: -140, right: -100, width: 420, height: 420, borderRadius: '50%', background: 'radial-gradient(circle, rgba(59,143,232,0.09) 0%, transparent 65%)', pointerEvents: 'none', zIndex: 0 }} />
      <div style={{ position: 'fixed', bottom: -120, left: -80, width: 360, height: 360, borderRadius: '50%', background: 'radial-gradient(circle, rgba(247,169,124,0.07) 0%, transparent 65%)', pointerEvents: 'none', zIndex: 0 }} />

      {/* Form column */}
      <div style={{ width: '100%', maxWidth: 430, position: 'relative', zIndex: 1 }}>

        {/* Logo */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, marginBottom: 28 }}>
          <KlaraLogo />
          <div style={{ fontSize: 26, fontWeight: 800, color: '#fff', letterSpacing: -0.5 }}>Klara</div>
          <div style={{ fontSize: 9.5, fontWeight: 600, color: 'rgba(247,169,124,0.6)', letterSpacing: 1.8, textTransform: 'uppercase' }}>
            Intelligent Travel Platform
          </div>
        </div>

        {/* Glass card */}
        <div style={{
          background: 'rgba(255,255,255,0.06)',
          border: '1px solid rgba(255,255,255,0.11)',
          borderRadius: 28,
          padding: '28px 24px 26px',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06), 0 24px 64px rgba(0,0,0,0.35)',
          backdropFilter: 'blur(20px)',
        }}>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', letterSpacing: -0.3, marginBottom: 4 }}>Welcome back</div>
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.42)', marginBottom: 24 }}>Sign in to your workspace</div>

          {/* Error */}
          {error && (
            <div style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.25)', borderRadius: 10, padding: '10px 14px', marginBottom: 16, fontSize: 12, color: '#F87171', display: 'flex', alignItems: 'center', gap: 8 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              {error}
            </div>
          )}

          {notice && (
            <div style={{ background: 'rgba(52,211,153,0.08)', border: '1px solid rgba(52,211,153,0.25)', borderRadius: 10, padding: '10px 14px', marginBottom: 16, fontSize: 12, color: '#34D399' }}>
              {notice}
            </div>
          )}

          {/* Email */}
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: 'block', fontSize: 9.5, fontWeight: 700, color: 'rgba(255,255,255,0.28)', letterSpacing: 0.9, textTransform: 'uppercase', marginBottom: 6 }}>Email</label>
            <div style={{ position: 'relative' }}>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="you@example.com"
                autoComplete="email"
                style={{
                  width: '100%', height: 50,
                  background: email ? 'rgba(59,143,232,0.06)' : 'rgba(255,255,255,0.07)',
                  border: email ? '1px solid rgba(59,143,232,0.35)' : '1px solid rgba(255,255,255,0.11)',
                  borderRadius: 13, padding: '0 46px 0 16px',
                  fontSize: 14, color: '#fff', outline: 'none',
                  transition: 'all 0.18s',
                }}
              />
              <div style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', color: 'rgba(255,255,255,0.28)' }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
              </div>
            </div>
          </div>

          {/* Password */}
          <div style={{ marginBottom: 8 }}>
            <label style={{ display: 'block', fontSize: 9.5, fontWeight: 700, color: 'rgba(255,255,255,0.28)', letterSpacing: 0.9, textTransform: 'uppercase', marginBottom: 6 }}>Password</label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Enter your password"
                autoComplete="current-password"
                style={{
                  width: '100%', height: 50,
                  background: password ? 'rgba(59,143,232,0.06)' : 'rgba(255,255,255,0.07)',
                  border: password ? '1px solid rgba(59,143,232,0.35)' : '1px solid rgba(255,255,255,0.11)',
                  borderRadius: 13, padding: '0 46px 0 16px',
                  fontSize: showPw ? 14 : 16, color: '#fff', outline: 'none',
                  letterSpacing: showPw ? 0 : 3,
                  transition: 'all 0.18s',
                }}
              />
              <button
                onClick={() => setShowPw(!showPw)}
                style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.3)', display: 'flex', alignItems: 'center', padding: 4 }}
              >
                <EyeIcon open={showPw} />
              </button>
            </div>
          </div>

          {/* Forgot */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 20 }}>
            <span
              onClick={handleForgot}
              style={{ fontSize: 12, fontWeight: 500, color: '#F7A97C', cursor: 'pointer' }}
            >
              Forgot password?
            </span>
          </div>

          {/* Sign in button */}
          <button
            onClick={handleLogin}
            disabled={loading}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              width: '100%', height: 50, borderRadius: 14, border: 'none',
              background: 'linear-gradient(135deg, #3B8FE8, #1D65C4)',
              boxShadow: '0 4px 20px rgba(59,143,232,0.3)',
              fontSize: 14, fontWeight: 700, color: '#fff', cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.75 : 1, marginBottom: 14,
              transition: 'opacity 0.18s',
            }}
          >
            {loading ? (
              <>
                <div style={{ width: 16, height: 16, borderRadius: '50%', border: '2px solid rgba(255,255,255,0.25)', borderTopColor: '#fff', animation: 'spin 0.65s linear infinite' }} />
                Signing in…
              </>
            ) : 'Sign In →'}
          </button>

          {/* OR divider */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '4px 0 14px' }}>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.08)' }} />
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.22)', fontWeight: 500 }}>or</span>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.08)' }} />
          </div>

          {/* Google */}
          <button
            onClick={handleGoogle}
            disabled={loading}
            style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
            width: '100%', height: 50, borderRadius: 14,
            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
            fontSize: 13, fontWeight: 600, color: 'rgba(255,255,255,0.7)', cursor: 'pointer',
            marginBottom: 0,
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continue with Google
          </button>

          {/* Footer */}
          <div style={{ textAlign: 'center', marginTop: 20, fontSize: 13, color: 'rgba(255,255,255,0.32)' }}>
            New here?{' '}
            <span
              onClick={() => navigate('/onboarding/personal-info')}
              style={{ color: '#F7A97C', fontWeight: 600, cursor: 'pointer' }}
            >
              Create account
            </span>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        input::placeholder { color: rgba(255,255,255,0.22); }
        input:focus { border-color: rgba(59,143,232,0.55) !important; background: rgba(59,143,232,0.07) !important; box-shadow: 0 0 0 3px rgba(59,143,232,0.12) !important; }
      `}</style>
    </div>
  )
}