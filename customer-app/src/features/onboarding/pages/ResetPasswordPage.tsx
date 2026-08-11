import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { authApi } from '../../../lib/api'
import PasswordStrength, { scorePassword } from './PasswordStrength'

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

export default function ResetPasswordPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  async function handleReset() {
    if (!token) { setError('This reset link is invalid or expired. Request a new one.'); return }
    if (scorePassword(password).score < 2) { setError('Choose a stronger password'); return }
    if (password !== confirm) { setError('Passwords don\'t match'); return }
    setError('')
    setLoading(true)
    try {
      // NOTE: add resetPassword to lib/api.ts authApi, hitting POST /auth/password/reset
      await authApi.resetPassword({ token, password })
      setDone(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'This reset link is invalid or expired. Request a new one.')
    } finally {
      setLoading(false)
    }
  }

  const inputStyle = (hasValue: boolean): React.CSSProperties => ({
    width: '100%', height: 50,
    background: hasValue ? 'rgba(59,143,232,0.06)' : 'rgba(255,255,255,0.07)',
    border: hasValue ? '1px solid rgba(59,143,232,0.35)' : '1px solid rgba(255,255,255,0.11)',
    borderRadius: 13, padding: '0 46px 0 16px',
    fontSize: showPw ? 14 : 16, color: '#fff', outline: 'none',
    letterSpacing: showPw ? 0 : 3, transition: 'all 0.18s',
  })

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px 20px' }}>
      <div style={{ position: 'fixed', top: -140, right: -100, width: 420, height: 420, borderRadius: '50%', background: 'radial-gradient(circle, rgba(59,143,232,0.09) 0%, transparent 65%)', pointerEvents: 'none', zIndex: 0 }} />
      <div style={{ position: 'fixed', bottom: -120, left: -80, width: 360, height: 360, borderRadius: '50%', background: 'radial-gradient(circle, rgba(247,169,124,0.07) 0%, transparent 65%)', pointerEvents: 'none', zIndex: 0 }} />

      <div style={{ width: '100%', maxWidth: 430, position: 'relative', zIndex: 1 }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, marginBottom: 28 }}>
          <KlaraLogo />
          <div style={{ fontSize: 26, fontWeight: 800, color: '#fff', letterSpacing: -0.5 }}>Klara</div>
        </div>

        <div style={{
          background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.11)',
          borderRadius: 28, padding: '28px 24px 26px',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06), 0 24px 64px rgba(0,0,0,0.35)',
          backdropFilter: 'blur(20px)',
        }}>
          {!done ? (
            <>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', letterSpacing: -0.3, marginBottom: 4 }}>Set a new password</div>
              <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.42)', marginBottom: 24 }}>Make it something you haven't used before.</div>

              {error && (
                <div style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.25)', borderRadius: 10, padding: '10px 14px', marginBottom: 16, fontSize: 12, color: '#F87171', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                  {error}
                </div>
              )}

              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 9.5, fontWeight: 700, color: 'rgba(255,255,255,0.28)', letterSpacing: 0.9, textTransform: 'uppercase', marginBottom: 6 }}>New Password</label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showPw ? 'text' : 'password'} value={password}
                    onChange={e => { setPassword(e.target.value); setError('') }}
                    placeholder="Enter new password" autoComplete="new-password" autoFocus
                    style={inputStyle(!!password)}
                  />
                  <button onClick={() => setShowPw(!showPw)} style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.3)', display: 'flex', padding: 4 }}>
                    <EyeIcon open={showPw} />
                  </button>
                </div>
                <PasswordStrength password={password} />
              </div>

              <div style={{ marginBottom: 22 }}>
                <label style={{ display: 'block', fontSize: 9.5, fontWeight: 700, color: 'rgba(255,255,255,0.28)', letterSpacing: 0.9, textTransform: 'uppercase', marginBottom: 6 }}>Confirm Password</label>
                <input
                  type={showPw ? 'text' : 'password'} value={confirm}
                  onChange={e => { setConfirm(e.target.value); setError('') }}
                  placeholder="Re-enter new password" autoComplete="new-password"
                  style={inputStyle(!!confirm)}
                />
              </div>

              <button
                onClick={handleReset}
                disabled={loading}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                  width: '100%', height: 50, borderRadius: 14, border: 'none',
                  background: 'linear-gradient(135deg, #3B8FE8, #1D65C4)',
                  boxShadow: '0 4px 20px rgba(59,143,232,0.3)',
                  fontSize: 14, fontWeight: 700, color: '#fff', cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.75 : 1,
                }}
              >
                {loading ? (
                  <>
                    <div style={{ width: 16, height: 16, borderRadius: '50%', border: '2px solid rgba(255,255,255,0.25)', borderTopColor: '#fff', animation: 'spin 0.65s linear infinite' }} />
                    Resetting…
                  </>
                ) : 'Reset Password →'}
              </button>
            </>
          ) : (
            <>
              <div style={{ width: 56, height: 56, borderRadius: 17, background: 'rgba(52,211,153,0.1)', border: '1.5px solid rgba(52,211,153,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#34D399" strokeWidth="2" strokeLinecap="round"><polyline points="20,6 9,17 4,12"/></svg>
              </div>
              <div style={{ fontSize: 20, fontWeight: 800, color: '#fff', textAlign: 'center', marginBottom: 6 }}>Password updated</div>
              <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.45)', textAlign: 'center', marginBottom: 24 }}>You can sign in with your new password now.</div>
              <button onClick={() => navigate('/login')} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: '100%', height: 50, borderRadius: 14, border: 'none',
                background: 'linear-gradient(135deg, #3B8FE8, #1D65C4)',
                boxShadow: '0 4px 20px rgba(59,143,232,0.3)',
                fontSize: 14, fontWeight: 700, color: '#fff', cursor: 'pointer',
              }}>
                Sign In →
              </button>
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
