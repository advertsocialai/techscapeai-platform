import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOnboarding } from '../context/OnboardingContext'
import { authApi } from '../../../lib/api'

function BackArrow() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
      <polyline points="15,18 9,12 15,6"/>
    </svg>
  )
}

export default function OtpPage() {
  const navigate = useNavigate()
  const { email, setOtpVerified } = useOnboarding()

  const [digits, setDigits] = useState(['', '', '', '', '', ''])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [secondsLeft, setSecondsLeft] = useState(165)
  const [resendMsg, setResendMsg] = useState('')
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  // Auto-send OTP on mount
  useEffect(() => {
    const otpEmail = email || localStorage.getItem('klara_otp_email') || ''
    if (otpEmail) {
      authApi.sendOtp(otpEmail).catch(() => {})
   }
    inputRefs.current[0]?.focus()
  }, [])

  // Countdown timer
  useEffect(() => {
    if (secondsLeft <= 0) return
    const t = setInterval(() => setSecondsLeft(s => s - 1), 1000)
    return () => clearInterval(t)
  }, [secondsLeft])

  const timerText = secondsLeft > 0
    ? `Expires in ${String(Math.floor(secondsLeft / 60)).padStart(2, '0')}:${String(secondsLeft % 60).padStart(2, '0')}`
    : 'Code expired — please resend'

  function handleDigitChange(value: string, idx: number) {
    const val = value.replace(/\D/g, '')
    const newDigits = [...digits]
    newDigits[idx] = val ? val[val.length - 1] : ''
    setDigits(newDigits)
    setError('')
    if (val && idx < 5) inputRefs.current[idx + 1]?.focus()
  }

  
  function handleKeyDown(e: React.KeyboardEvent, idx: number) {
    if (e.key === 'Backspace') {
      const newDigits = [...digits]
      if (digits[idx]) {
        newDigits[idx] = ''
        setDigits(newDigits)
      } else if (idx > 0) {
        newDigits[idx - 1] = ''
        setDigits(newDigits)
        inputRefs.current[idx - 1]?.focus()
      }
    }
  }

  function handlePaste(e: React.ClipboardEvent) {
    e.preventDefault()
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (pasted.length === 6) {
      setDigits(pasted.split(''))
      inputRefs.current[5]?.focus()
    }
  }

  async function handleVerify() {
    const code = digits.join('')
    if (code.length < 6) { setError('Please enter all 6 digits'); return }
    setLoading(true)
    setError('')
    try {
      await authApi.verifyOtp(email, code)
      setOtpVerified(true)
      navigate('/onboarding/terms')
    } catch {
      setError('Invalid or expired OTP. Please try again.')
      setDigits(['', '', '', '', '', ''])
      inputRefs.current[0]?.focus()
    } finally {
      setLoading(false)
    }
  }

  async function handleResend() {
    setSecondsLeft(165)
    setDigits(['', '', '', '', '', ''])
    setError('')
    setResendMsg('New OTP sent!')
    setTimeout(() => setResendMsg(''), 3000)
    try { await authApi.sendOtp(email) } catch {}
    inputRefs.current[0]?.focus()
  }

  const allFilled = digits.every(d => d !== '')

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '32px 20px' }}>
      <div style={{ width: '100%', maxWidth: 430, position: 'relative', zIndex: 1 }}>

        {/* Back nav */}
        <div onClick={() => navigate('/onboarding/address')} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 20, cursor: 'pointer', color: 'rgba(255,255,255,0.45)', fontSize: 13, fontWeight: 500 }}>
          <BackArrow /> Address
        </div>

        <div style={{
          background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.11)',
          borderRadius: 28, padding: '28px 24px 26px',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06), 0 24px 64px rgba(0,0,0,0.35)',
          backdropFilter: 'blur(20px)',
        }}>

          {/* Progress */}
          <div style={{ display: 'flex', gap: 5, marginBottom: 20 }}>
            {[0,1,2,3].map(i => (
              <div key={i} style={{
                flex: 1, height: 3, borderRadius: 2,
                background: i < 2 ? '#F7A97C' : i === 2 ? '#3B8FE8' : 'rgba(255,255,255,0.1)'
              }} />
            ))}
          </div>

          {/* Icon */}
          <div style={{
            width: 60, height: 60, borderRadius: 18, margin: '0 auto 16px',
            background: 'rgba(59,143,232,0.10)', border: '1.5px solid rgba(59,143,232,0.35)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#3B8FE8" strokeWidth="2" strokeLinecap="round">
              <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
              <polyline points="22,6 12,13 2,6"/>
            </svg>
          </div>

          <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', textAlign: 'center', marginBottom: 4 }}>
            Almost there, traveler
          </div>
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.42)', textAlign: 'center', marginBottom: 16 }}>
            Enter the 6-digit code we sent to
          </div>

          {/* Email chip */}
          <div style={{
            background: 'rgba(59,143,232,0.10)', border: '1px solid rgba(59,143,232,0.25)',
            borderRadius: 10, padding: '10px 14px', marginBottom: 20,
            display: 'flex', alignItems: 'center', gap: 8,
            fontSize: 12, color: 'rgba(255,255,255,0.6)',
          }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#3B8FE8" strokeWidth="2" strokeLinecap="round">
              <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
              <polyline points="22,6 12,13 2,6"/>
            </svg>
            OTP sent to <strong style={{ color: '#fff' }}>{email || 'your email'}</strong>
          </div>

          {/* Error */}
          {error && (
            <div style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.25)', borderRadius: 10, padding: '10px 14px', marginBottom: 16, fontSize: 12, color: '#F87171', textAlign: 'center' }}>
              {error}
            </div>
          )}

          {/* OTP boxes */}
          <div style={{ display: 'flex', gap: 9, justifyContent: 'center', marginBottom: 16 }} onPaste={handlePaste}>
            {digits.map((digit, idx) => (
              <div key={idx} style={{
                width: 48, height: 58, borderRadius: 13,
                background: digit ? 'rgba(59,143,232,0.10)' : 'rgba(255,255,255,0.07)',
                border: `${digit ? '1.5px' : '1px'} solid ${digit ? '#3B8FE8' : 'rgba(255,255,255,0.11)'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 22, fontWeight: 700, color: '#fff',
                position: 'relative', transition: 'all 0.15s',
                boxShadow: digit ? '0 0 0 3px rgba(59,143,232,0.12)' : 'none',
              }}>
                <span style={{ pointerEvents: 'none' }}>{digit}</span>
                <input
                  ref={el => { inputRefs.current[idx] = el }}
                  type="tel"
                  maxLength={1}
                  value=""
                  onChange={e => handleDigitChange(e.target.value, idx)}
                  onKeyDown={e => handleKeyDown(e, idx)}
                  style={{
                    position: 'absolute', inset: 0, opacity: 0,
                    width: '100%', height: '100%', cursor: 'text',
                    fontSize: 22, textAlign: 'center',
                  }}
                />
              </div>
            ))}
          </div>

          {/* Resend */}
          <div style={{ textAlign: 'center', marginBottom: 4 }}>
            {resendMsg ? (
              <span style={{ fontSize: 12, color: '#34D399' }}>{resendMsg}</span>
            ) : (
              <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)' }}>
                Didn't receive it?{' '}
                <span onClick={handleResend} style={{ color: '#F7A97C', fontWeight: 600, cursor: 'pointer' }}>
                  Resend OTP
                </span>
              </span>
            )}
          </div>

          {/* Timer */}
          <div style={{
            textAlign: 'center', fontSize: 11, marginBottom: 22,
            color: secondsLeft <= 0 ? '#F87171' : 'rgba(255,255,255,0.18)',
          }}>
            {timerText}
          </div>

          {/* Verify button */}
          <button
            onClick={handleVerify}
            disabled={loading || !allFilled}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              width: '100%', height: 50, borderRadius: 14, border: 'none',
              background: 'linear-gradient(135deg, #3B8FE8, #1D65C4)',
              boxShadow: '0 4px 20px rgba(59,143,232,0.3)',
              fontSize: 14, fontWeight: 700, color: '#fff',
              cursor: loading || !allFilled ? 'not-allowed' : 'pointer',
              opacity: loading || !allFilled ? 0.55 : 1,
              marginBottom: 10, transition: 'opacity 0.18s',
            }}
          >
            {loading ? (
              <>
                <div style={{ width: 16, height: 16, borderRadius: '50%', border: '2px solid rgba(255,255,255,0.25)', borderTopColor: '#fff', animation: 'spin 0.65s linear infinite' }} />
                Verifying…
              </>
            ) : 'Verify & Continue →'}
          </button>

          {/* Back */}
          <button onClick={() => navigate('/onboarding/address')} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: '100%', height: 50, borderRadius: 14,
            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
            fontSize: 13, fontWeight: 600, color: 'rgba(255,255,255,0.5)', cursor: 'pointer',
          }}>
            ← Back
          </button>
        </div>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}