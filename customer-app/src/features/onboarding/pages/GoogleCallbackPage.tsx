import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { authApi } from '../../../lib/api'
// ^ adjust import path to match where LoginPage.tsx imports authApi from

export default function GoogleCallbackPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [error, setError] = useState('')

  useEffect(() => {
    async function run() {
      const code = params.get('code')
      const returnedState = params.get('state')
      const savedState = sessionStorage.getItem('google_oauth_state')
      sessionStorage.removeItem('google_oauth_state')

      if (!code) {
        setError('Google sign-in was cancelled or failed.')
        return
      }
      if (savedState && returnedState && savedState !== returnedState) {
        // CSRF guard — the state we sent doesn't match what came back
        setError('Something looked off with that sign-in attempt. Please try again.')
        return
      }

      try {
        const redirectUri = `${window.location.origin}/auth/google/callback`
        const res = await authApi.googleOAuthCallback(code, redirectUri)
        localStorage.setItem('access_token', res.data.access_token)
        localStorage.setItem('refresh_token', res.data.refresh_token)
        navigate('/dashboard')
      } catch (err: any) {
        setError('Could not complete Google sign-in. Please try again.')
      }
    }
    run()
  }, [])

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px 20px' }}>
      <div style={{ width: '100%', maxWidth: 430, textAlign: 'center' }}>
        {!error ? (
          <>
            <div style={{ width: 40, height: 40, borderRadius: '50%', border: '3px solid rgba(255,255,255,0.15)', borderTopColor: '#3B8FE8', margin: '0 auto 16px', animation: 'spin 0.7s linear infinite' }} />
            <div style={{ fontSize: 14, color: 'rgba(255,255,255,0.5)' }}>Finishing sign-in with Google…</div>
          </>
        ) : (
          <>
            <div style={{ fontSize: 14, color: '#F87171', marginBottom: 16 }}>{error}</div>
            <button
              onClick={() => navigate('/onboarding/login')}
              style={{
                height: 46, padding: '0 24px', borderRadius: 14, border: 'none',
                background: 'linear-gradient(135deg, #3B8FE8, #1D65C4)',
                fontSize: 13, fontWeight: 700, color: '#fff', cursor: 'pointer',
              }}
            >
              Back to Sign In
            </button>
          </>
        )}
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
