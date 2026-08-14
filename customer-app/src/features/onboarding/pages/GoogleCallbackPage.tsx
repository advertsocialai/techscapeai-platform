import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import api, { setSession } from '../../../lib/api'
import { errorMessage } from '../../../lib/errors'
import type { LoginResponse } from '../../../types/auth'

/**
 * Lands here after the user approves (or declines) Google's consent screen.
 * `handleGoogle()` in LoginPage sent the browser to Google with
 * `redirect_uri = {OAUTH_REDIRECT_BASE}/auth/google/callback` — this route
 * MUST match that path exactly, or Google rejects the round trip before it
 * ever reaches this component.
 *
 * The backend's GET /auth/oauth/google/callback does the actual code↔token
 * exchange server-side (client secret never touches the browser); this page's
 * only job is to hand it the `code` Google appended to the URL, then store
 * the returned tokens the SAME way password login does (`setSession`).
 */
export default function GoogleCallbackPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [error, setError] = useState('')
  // StrictMode double-invokes effects in dev; an authorization `code` is
  // single-use, so a second exchange attempt would 401 even though the first
  // one succeeded. Guard so only one exchange ever fires per mount.
  const exchanged = useRef(false)

  useEffect(() => {
    if (exchanged.current) return
    exchanged.current = true

    const code = searchParams.get('code')
    const providerError = searchParams.get('error')

    if (providerError) {
      setError(
        providerError === 'access_denied'
          ? 'Google sign-in was cancelled.'
          : `Google sign-in failed: ${providerError}`,
      )
      return
    }
    if (!code) {
      setError('Google did not return an authorization code. Please try again.')
      return
    }

    api
      .get<LoginResponse>('/auth/oauth/google/callback', { params: { code } })
      .then((res) => {
        setSession(res.data.access_token, res.data.refresh_token)
        navigate('/dashboard', { replace: true })
      })
      .catch((err) => setError(errorMessage(err)))
  }, [searchParams, navigate])

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 16,
        padding: '24px 20px',
        textAlign: 'center',
      }}
    >
      {error ? (
        <>
          <div
            style={{
              background: 'rgba(248,113,113,0.08)',
              border: '1px solid rgba(248,113,113,0.25)',
              borderRadius: 10,
              padding: '12px 18px',
              fontSize: 13,
              color: '#F87171',
              maxWidth: 380,
            }}
          >
            {error}
          </div>
          <span
            onClick={() => navigate('/onboarding/login', { replace: true })}
            style={{ fontSize: 13, fontWeight: 600, color: '#F7A97C', cursor: 'pointer' }}
          >
            Back to sign in
          </span>
        </>
      ) : (
        <>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              border: '2.5px solid rgba(255,255,255,0.15)',
              borderTopColor: '#3B8FE8',
              animation: 'spin 0.7s linear infinite',
            }}
          />
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)' }}>
            Finishing Google sign-in…
          </div>
        </>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
