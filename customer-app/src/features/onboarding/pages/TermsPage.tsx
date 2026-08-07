import { useState } from 'react'
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

function CheckIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
      <polyline points="2,6 5,9 10,3" stroke="white" strokeWidth="2.2" strokeLinecap="round"/>
    </svg>
  )
}

interface CheckItemProps {
  checked: boolean
  onChange: (v: boolean) => void
  children: React.ReactNode
  required?: boolean
}

function CheckItem({ checked, onChange, children, required }: CheckItemProps) {
  return (
    <div
      onClick={() => onChange(!checked)}
      style={{
        display: 'flex', gap: 12, alignItems: 'flex-start',
        padding: '12px 14px', borderRadius: 12, cursor: 'pointer',
        background: checked ? 'rgba(59,143,232,0.08)' : 'rgba(255,255,255,0.03)',
        border: `1px solid ${checked ? 'rgba(59,143,232,0.30)' : 'rgba(255,255,255,0.07)'}`,
        marginBottom: 10, transition: 'all 0.15s',
      }}
    >
      <div style={{
        width: 20, height: 20, borderRadius: 6, flexShrink: 0, marginTop: 1,
        background: checked ? '#3B8FE8' : 'rgba(255,255,255,0.05)',
        border: `1.5px solid ${checked ? '#3B8FE8' : 'rgba(255,255,255,0.2)'}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'all 0.15s',
      }}>
        {checked && <CheckIcon />}
      </div>
      <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.75)', lineHeight: 1.55 }}>
        {children}
        {required && <span style={{ color: '#F87171', marginLeft: 4, fontSize: 10 }}>*</span>}
      </div>
    </div>
  )
}

export default function TermsPage() {
  const navigate = useNavigate()
  const ctx = useOnboarding()

  const [terms, setTerms] = useState(false)
  const [age, setAge] = useState(false)
  const [marketing, setMarketing] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const canSubmit = terms && age

  async function handleCreate() {
    if (!canSubmit) return
    setLoading(true)
    setError('')

    const payload = {
      user_first_name: ctx.firstName,
      user_last_name: ctx.lastName,
      contact_email: ctx.email,
      contact_phone: `${ctx.countryCode}${ctx.phone}`,
      user_password: ctx.password,
      business_name: ctx.company || `${ctx.firstName}'s Account`,
      industry: 'travel',
      website_url: '',
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      terms_accepted_at: new Date().toISOString(),
      terms_version: 'v1.0',
      marketing_opt_in: marketing,
    }

    try {
      await authApi.register(payload)
      ctx.setTerms({ termsAccepted: terms, ageConfirmed: age, marketingOptIn: marketing })
      navigate('/onboarding/success')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(detail || 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '32px 20px' }}>
      <div style={{ width: '100%', maxWidth: 430, position: 'relative', zIndex: 1 }}>

        {/* Back */}
        <div onClick={() => navigate('/onboarding/otp')} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 20, cursor: 'pointer', color: 'rgba(255,255,255,0.45)', fontSize: 13, fontWeight: 500 }}>
          <BackArrow /> OTP Verification
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
                background: i < 3 ? '#F7A97C' : '#3B8FE8'
              }} />
            ))}
          </div>

          {/* Shield icon */}
          <div style={{
            width: 60, height: 60, borderRadius: 18, margin: '0 auto 16px',
            background: 'rgba(247,169,124,0.10)', border: '1.5px solid rgba(247,169,124,0.30)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#F7A97C" strokeWidth="2" strokeLinecap="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>

          <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', textAlign: 'center', letterSpacing: -0.3, marginBottom: 4 }}>
            Your journey. Your rules.
          </div>
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.42)', textAlign: 'center', marginBottom: 22 }}>
            Step 4 of 4 — Just a few agreements
          </div>

          {/* Error */}
          {error && (
            <div style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.25)', borderRadius: 10, padding: '10px 14px', marginBottom: 16, fontSize: 12, color: '#F87171', textAlign: 'center' }}>
              {error}
            </div>
          )}

          {/* Checkboxes */}
          <CheckItem checked={terms} onChange={setTerms} required>
            I agree to the{' '}
            <span style={{ color: '#F7A97C', fontWeight: 600 }}>Terms of Service</span>
            {' '}and{' '}
            <span style={{ color: '#F7A97C', fontWeight: 600 }}>Privacy Policy</span>
          </CheckItem>

          <CheckItem checked={age} onChange={setAge} required>
            I confirm I am 18+ and my information is accurate
          </CheckItem>

          <div style={{ marginBottom: 22 }}>
            <CheckItem checked={marketing} onChange={setMarketing}>
              Send me travel deals and exclusive offers{' '}
              <span style={{ color: '#F7A97C', fontWeight: 600 }}>(optional)</span>
            </CheckItem>
          </div>

          {/* Required note */}
          <div style={{ fontSize: 10.5, color: 'rgba(255,255,255,0.22)', marginBottom: 16, textAlign: 'center' }}>
            <span style={{ color: '#F87171' }}>*</span> Required to create your account
          </div>

          {/* Create account */}
          <button
            onClick={handleCreate}
            disabled={!canSubmit || loading}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              width: '100%', height: 50, borderRadius: 14, border: 'none',
              background: 'linear-gradient(135deg, #F7A97C, #e07a3a)',
              boxShadow: canSubmit ? '0 4px 20px rgba(247,169,124,0.25)' : 'none',
              fontSize: 14, fontWeight: 700, color: '#fff',
              cursor: !canSubmit || loading ? 'not-allowed' : 'pointer',
              opacity: !canSubmit || loading ? 0.45 : 1,
              marginBottom: 10, transition: 'all 0.18s',
            }}
          >
            {loading ? (
              <>
                <div style={{ width: 16, height: 16, borderRadius: '50%', border: '2px solid rgba(255,255,255,0.25)', borderTopColor: '#fff', animation: 'spin 0.65s linear infinite' }} />
                Creating account…
              </>
            ) : '🎉 Create My Account'}
          </button>

          {/* Back */}
          <button onClick={() => navigate('/onboarding/otp')} style={{
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