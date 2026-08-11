import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../../../lib/api'

// ── Klara Logo (mirrors LoginPage.tsx) ─────────────────
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

export default function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)

  async function handleSend() {
    if (!email.trim()) { setError('Enter the email on your account'); return }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) { setError('Enter a valid email address'); return }
    setError('')
    setLoading(true)
    try {
      // NOTE: add forgotPassword to lib/api.ts authApi, hitting POST /auth/password/forgot
      await authApi.forgotPassword(email.trim())
      setSent(true)
    } catch (err: any) {
      // Don't reveal whether the email exists — show the same success state either way
      // unless it's a rate-limit / network error worth surfacing.
      if (err.response?.status === 429) {
        setError('Too many attempts. Try again in a few minutes.')
      } else {
        setSent(true)
      }
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleSend()
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px 20px' }}>
      <div style={{ position: 'fixed', top: -140, right: -100, width: 420, height: 420, borderRadius: '50%', background: 'radial-gradient(circle, rgba(59,143,232,0.09) 0%, transparent 65%)', pointerEvents: 'none', zIndex: 0 }} />
      <div style={{ position: 'fixed', bottom: -120, left: -80, width: 360, height: 360, borderRadius: '50%', background: 'radial-gradient(circle, rgba(247,169,124,0.07) 0%, transparent 65%)', pointerEvents: 'none', zIndex: 0 }} />

      <div style={{ width: '100%', maxWidth: 430, position: 'relative', zIndex: 1 }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, marginBottom: 28 }}>
          <KlaraLogo />
          <div style={{ fontSize: 26, fontWeight: 800, color: '#fff', letterSpacing: -0.5 }}>Klara</div>
          <div style={{ fontSize: 9.5, fontWeight: 600, color: 'rgba(247,169,124,0.6)', letterSpacing: 1.8, textTransform: 'uppercase' }}>
            Intelligent Travel Platform
          </div>
        </div>

        <div style={{
          background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.11)',
          borderRadius: 28, padding: '28px 24px 26px',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06), 0 24px 64px rgba(0,0,0,0.35)',
          backdropFilter: 'blur(20px)',
        }}>
          {!sent ? (
            <>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', letterSpacing: -0.3, marginBottom: 4 }}>Forgot password?</div>
              <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.42)', marginBottom: 24 }}>
                Enter your account email — we'll send a reset link.
              </div>

              {error && (
                <div style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.25)', borderRadius: 10, padding: '10px 14px', marginBottom: 16, fontSize: 12, color: '#F87171', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                  {error}
                </div>
              )}

              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: 9.5, fontWeight: 700, color: 'rgba(255,255,255,0.28)', letterSpacing: 0.9, textTransform: 'uppercase', marginBottom: 6 }}>Email</label>
                <input
                  type="email" value={email}
                  onChange={e => { setEmail(e.target.value); setError('') }}
                  onKeyDown={handleKeyDown}
                  placeholder="you@example.com"
                  autoComplete="email" autoFocus
                  style={{
                    width: '100%', height: 50,
                    background: email ? 'rgba(59,143,232,0.06)' : 'rgba(255,255,255,0.07)',
                    border: email ? '1px solid rgba(59,143,232,0.35)' : '1px solid rgba(255,255,255,0.11)',
                    borderRadius: 13, padding: '0 16px',
                    fontSize: 14, color: '#fff', outline: 'none', transition: 'all 0.18s',
                  }}
                />
              </div>

              <button
                onClick={handleSend}
                disabled={loading}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                  width: '100%', height: 50, borderRadius: 14, border: 'none',
                  background: 'linear-gradient(135deg, #3B8FE8, #1D65C4)',
                  boxShadow: '0 4px 20px rgba(59,143,232,0.3)',
                  fontSize: 14, fontWeight: 700, color: '#fff', cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.75 : 1, marginBottom: 12,
                }}
              >
                {loading ? (
                  <>
                    <div style={{ width: 16, height: 16, borderRadius: '50%', border: '2px solid rgba(255,255,255,0.25)', borderTopColor: '#fff', animation: 'spin 0.65s linear infinite' }} />
                    Sending…
                  </>
                ) : 'Send Reset Link →'}
              </button>

              <button onClick={() => navigate('/login')} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: '100%', height: 44, borderRadius: 14, background: 'transparent', border: 'none',
                fontSize: 12.5, fontWeight: 500, color: 'rgba(255,255,255,0.4)', cursor: 'pointer',
              }}>
                ← Back to sign in
              </button>
            </>
          ) : (
            <>
              <div style={{ width: 56, height: 56, borderRadius: 17, background: 'rgba(52,211,153,0.1)', border: '1.5px solid rgba(52,211,153,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#34D399" strokeWidth="2" strokeLinecap="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
              </div>
              <div style={{ fontSize: 20, fontWeight: 800, color: '#fff', textAlign: 'center', marginBottom: 6 }}>Check your email</div>
              <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.45)', textAlign: 'center', marginBottom: 24, lineHeight: 1.5 }}>
                If an account exists for <b style={{ color: 'rgba(255,255,255,0.7)' }}>{email}</b>, a reset link is on its way. It expires in 30 minutes.
              </div>
              <button onClick={() => navigate('/login')} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: '100%', height: 50, borderRadius: 14, border: 'none',
                background: 'linear-gradient(135deg, #3B8FE8, #1D65C4)',
                boxShadow: '0 4px 20px rgba(59,143,232,0.3)',
                fontSize: 14, fontWeight: 700, color: '#fff', cursor: 'pointer', marginBottom: 10,
              }}>
                Back to Sign In
              </button>
              <div style={{ textAlign: 'center' }}>
                <span onClick={() => setSent(false)} style={{ fontSize: 12, color: '#F7A97C', fontWeight: 600, cursor: 'pointer' }}>
                  Didn't get it? Try a different email
                </span>
              </div>
            </>
          )}
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        input::placeholder { color: rgba(255,255,255,0.22); }
        input:focus { border-color: rgba(59,143,232,0.55) !important; box-shadow: 0 0 0 3px rgba(59,143,232,0.12) !important; outline: none !important; }
      `}</style>
    </div>
  )
}
