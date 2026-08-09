/**
 * Traveller sign-in — email, then a 6-digit code.
 *
 * WHY A SEPARATE SCREEN FROM /onboarding/login
 * --------------------------------------------
 * A traveller has NO PASSWORD. They are a `travel_customer_profiles` row, not a
 * `ts_users` row, so the agency login form (email + password -> /auth/login)
 * can never work for them — it would collect a credential that does not exist
 * and fail every time.
 *
 * This screen appeared the moment the trip surface stopped serving fixtures:
 * `/trip` now requires a traveller token, and until this existed the guard
 * bounced travellers to a form they could not complete. A guard with nowhere to
 * send people is a dead end, not security.
 *
 * The backend deliberately answers `request-otp` with 202 whether or not the
 * address belongs to a customer — it will not confirm who is a customer of
 * which agency. This screen keeps that promise: it advances to the code step
 * either way, and says "if that address is on a booking". Telling the user
 * "no such customer" would hand an enumeration oracle to anyone with the URL.
 */
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { errorMessage } from '../../lib/errors'
import { travellerApi } from '../../lib/travellerApi'
import { colors, layout, radii } from '../../styles/tokens'

type Step = 'email' | 'code'

export default function TravellerLoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from || '/trip'

  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function requestCode() {
    if (!email.trim()) {
      setError('Enter the email address on your booking')
      return
    }
    setBusy(true)
    setError('')
    try {
      await travellerApi.requestOtp(email.trim())
      setStep('code')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function verify() {
    if (code.trim().length < 4) {
      setError('Enter the code from your email')
      return
    }
    setBusy(true)
    setError('')
    try {
      await travellerApi.verifyOtp(email.trim(), code.trim())
      navigate(from, { replace: true })
    } catch (err) {
      // A wrong code and an unknown address return the SAME 401 with the same
      // wording, by design — so this message must not try to distinguish them.
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const input: React.CSSProperties = {
    width: '100%',
    height: layout.inputHeight,
    background: colors.inputBg,
    border: `1px solid ${colors.inputBorder}`,
    borderRadius: radii.input,
    padding: '0 16px',
    fontSize: 14,
    color: colors.textPrimary,
    outline: 'none',
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px 20px',
      }}
    >
      <div style={{ width: '100%', maxWidth: layout.maxWidth }}>
        <div
          style={{
            background: colors.surface,
            border: `1px solid ${colors.surfaceBorder}`,
            borderRadius: radii.card,
            padding: '28px 24px 26px',
            backdropFilter: 'blur(20px)',
          }}
        >
          <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>
            {step === 'email' ? 'View your trip' : 'Check your email'}
          </div>
          <div style={{ fontSize: 13, color: colors.textSecondary, marginBottom: 22 }}>
            {step === 'email'
              ? 'Enter the email address on your booking and we’ll send you a code.'
              : `If ${email} is on a booking, a 6-digit code is on its way.`}
          </div>

          {error && (
            <div
              style={{
                background: colors.errorDim,
                border: `1px solid ${colors.error}40`,
                borderRadius: 10,
                padding: '10px 14px',
                marginBottom: 16,
                fontSize: 12,
                color: colors.error,
              }}
            >
              {error}
            </div>
          )}

          {step === 'email' ? (
            <>
              <input
                type="email"
                inputMode="email"
                autoComplete="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                  setError('')
                }}
                onKeyDown={(e) => e.key === 'Enter' && requestCode()}
                placeholder="you@example.com"
                style={{ ...input, marginBottom: 16 }}
              />
              <button
                onClick={requestCode}
                disabled={busy}
                style={{
                  width: '100%',
                  height: layout.buttonHeight,
                  borderRadius: radii.button,
                  border: 'none',
                  background: colors.blueGrad,
                  color: '#fff',
                  fontSize: 14,
                  fontWeight: 700,
                  cursor: busy ? 'not-allowed' : 'pointer',
                  opacity: busy ? 0.7 : 1,
                }}
              >
                {busy ? 'Sending…' : 'Send me a code'}
              </button>
            </>
          ) : (
            <>
              <input
                // inputMode numeric + one-time-code so mobile keyboards show
                // digits and iOS/Android can autofill the SMS/email code.
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onChange={(e) => {
                  setCode(e.target.value.replace(/\D/g, '').slice(0, 6))
                  setError('')
                }}
                onKeyDown={(e) => e.key === 'Enter' && verify()}
                placeholder="6-digit code"
                style={{
                  ...input,
                  marginBottom: 16,
                  letterSpacing: 6,
                  fontSize: 18,
                  textAlign: 'center',
                }}
              />
              <button
                onClick={verify}
                disabled={busy}
                style={{
                  width: '100%',
                  height: layout.buttonHeight,
                  borderRadius: radii.button,
                  border: 'none',
                  background: colors.blueGrad,
                  color: '#fff',
                  fontSize: 14,
                  fontWeight: 700,
                  cursor: busy ? 'not-allowed' : 'pointer',
                  opacity: busy ? 0.7 : 1,
                  marginBottom: 12,
                }}
              >
                {busy ? 'Checking…' : 'View my trip →'}
              </button>
              <button
                onClick={() => {
                  setStep('email')
                  setCode('')
                  setError('')
                }}
                style={{
                  width: '100%',
                  height: layout.buttonHeight,
                  borderRadius: radii.button,
                  background: colors.inputBg,
                  border: `1px solid ${colors.inputBorder}`,
                  color: colors.textSecondary,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                ← Use a different email
              </button>
            </>
          )}
        </div>

        <div
          style={{
            textAlign: 'center',
            marginTop: 18,
            fontSize: 12,
            color: colors.textLabel,
            lineHeight: 1.6,
          }}
        >
          Booked through an agency? Use the email you gave them.
          <br />
          No code arrives if that address isn’t on a booking.
        </div>
      </div>
    </div>
  )
}
