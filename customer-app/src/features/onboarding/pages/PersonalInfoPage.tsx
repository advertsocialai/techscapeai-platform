import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOnboarding } from '../context/OnboardingContext'
import { isPasswordValid, passwordErrors } from '../../../lib/passwordValidation'
import PasswordRequirements from '../PasswordRequirements'

function BackArrow() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
      <polyline points="15,18 9,12 15,6"/>
    </svg>
  )
}

function EyeIcon({ open }: { open: boolean }) {
  return open ? (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  ) : (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  )
}

// Reusable field styles
const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 9.5, fontWeight: 700,
  color: 'rgba(255,255,255,0.28)', letterSpacing: 0.9,
  textTransform: 'uppercase', marginBottom: 6,
}

function inputStyle(hasValue: boolean): React.CSSProperties {
  return {
    width: '100%', height: 50,
    background: hasValue ? 'rgba(59,143,232,0.06)' : 'rgba(255,255,255,0.07)',
    border: hasValue ? '1px solid rgba(59,143,232,0.35)' : '1px solid rgba(255,255,255,0.11)',
    borderRadius: 13, padding: '0 46px 0 16px',
    fontSize: 14, color: '#fff', outline: 'none',
    transition: 'all 0.18s',
  }
}

export default function PersonalInfoPage() {
  const navigate = useNavigate()
  const { setPersonalInfo } = useOnboarding()

  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [countryCode, setCountryCode] = useState('+91')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [showCpw, setShowCpw] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  function validate() {
    const e: Record<string, string> = {}
    if (!firstName.trim()) e.firstName = 'First name is required'
    if (!lastName.trim()) e.lastName = 'Last name is required'
    const freeEmailDomains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com', 'aol.com', 'protonmail.com', 'live.com', 'rediffmail.com']
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!email.trim() || !emailRegex.test(email)) {
      e.email = 'Please enter a valid email address'
    } else {
      const domain = email.split('@')[1]?.toLowerCase()
      if (freeEmailDomains.includes(domain)) {
        e.email = 'Please use your business email, not a personal one'
      }
    }
    const phoneDigits = phone.replace(/\D/g, '')
    const phoneLengths: Record<string, number> = { '+91': 10, '+1': 10, '+44': 10, '+971': 9, '+65': 8 }
    if (!phone.trim()) {
      e.phone = 'Phone number is required'
    } else if (phoneDigits.length !== phoneLengths[countryCode]) {
      e.phone = `Enter a valid ${phoneLengths[countryCode]}-digit phone number`
    }
    // Mirrors the server's policy exactly (lib/passwordValidation.ts). This used
    // to be a length-only check, so a password the client accepted was rejected
    // by the backend four screens later.
    if (!isPasswordValid(password)) {
      e.password = `Password needs ${passwordErrors(password).join(', ').toLowerCase()}`
    }
    if (password !== confirmPassword) e.confirmPassword = 'Passwords do not match'
    return e
  }

  function handleContinue() {
    const e = validate()
    if (Object.keys(e).length > 0) { setErrors(e); return }
    setPersonalInfo({ firstName, lastName, email, phone, countryCode, password })
    localStorage.setItem('klara_otp_email', email)
    navigate('/onboarding/address')
  }

  const field = (label: string, value: string, setter: (v: string) => void, placeholder: string, type = 'text', errorKey = '') => (
    <div style={{ marginBottom: 14 }}>
      <label style={labelStyle}>{label}</label>
      <input
        type={type}
        value={value}
        onChange={e => { setter(e.target.value); setErrors(prev => ({ ...prev, [errorKey]: '' })) }}
        placeholder={placeholder}
        style={{
          ...inputStyle(!!value),
          borderColor: errors[errorKey] ? 'rgba(248,113,113,0.5)' : (value ? 'rgba(59,143,232,0.35)' : 'rgba(255,255,255,0.11)'),
          background: errors[errorKey] ? 'rgba(248,113,113,0.06)' : (value ? 'rgba(59,143,232,0.06)' : 'rgba(255,255,255,0.07)'),
        }}
      />
      {errors[errorKey] && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors[errorKey]}</div>}
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '32px 20px 40px' }}>
      <div style={{ width: '100%', maxWidth: 430, position: 'relative', zIndex: 1 }}>

        {/* Back nav */}
        <div onClick={() => navigate('/onboarding/login')} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 20, cursor: 'pointer', color: 'rgba(255,255,255,0.45)', fontSize: 13, fontWeight: 500 }}>
          <BackArrow /> Back to sign in
        </div>

        <div style={{
          background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.11)',
          borderRadius: 28, padding: '28px 24px 26px',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06), 0 24px 64px rgba(0,0,0,0.35)',
          backdropFilter: 'blur(20px)',
        }}>

          {/* Progress bar */}
          <div style={{ display: 'flex', gap: 5, marginBottom: 20 }}>
            {[0,1,2,3].map(i => (
              <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: i === 0 ? '#3B8FE8' : 'rgba(255,255,255,0.1)' }} />
            ))}
          </div>

          <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', letterSpacing: -0.3, marginBottom: 4 }}>
            The world is waiting for you 🌍
          </div>
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.42)', marginBottom: 22 }}>
            Step 1 of 4 — Personal Info
          </div>

          {/* First + Last name grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>First Name</label>
              <input type="text" value={firstName} onChange={e => { setFirstName(e.target.value); setErrors(p => ({...p, firstName:''})) }} placeholder="John"
                style={{ ...inputStyle(!!firstName), borderColor: errors.firstName ? 'rgba(248,113,113,0.5)' : (firstName ? 'rgba(59,143,232,0.35)' : 'rgba(255,255,255,0.11)') }} />
              {errors.firstName && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.firstName}</div>}
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Last Name</label>
              <input type="text" value={lastName} onChange={e => { setLastName(e.target.value); setErrors(p => ({...p, lastName:''})) }} placeholder="Smith"
                style={{ ...inputStyle(!!lastName), borderColor: errors.lastName ? 'rgba(248,113,113,0.5)' : (lastName ? 'rgba(59,143,232,0.35)' : 'rgba(255,255,255,0.11)') }} />
              {errors.lastName && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.lastName}</div>}
            </div>
          </div>

          {/* Email */}
          {field('Business Email', email, setEmail, 'you@company.com', 'email', 'email')}

          {/* Phone with country code */}
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Phone Number</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <select aria-label="Country code" value={countryCode} onChange={e => setCountryCode(e.target.value)} style={{
                height: 50, background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.11)',
                borderRadius: 13, padding: '0 12px', fontSize: 13, color: 'rgba(255,255,255,0.7)',
                outline: 'none', cursor: 'pointer', flexShrink: 0,
              }}>
                <option value="+91">🇮🇳 +91</option>
                <option value="+1">🇺🇸 +1</option>
                <option value="+44">🇬🇧 +44</option>
                <option value="+971">🇦🇪 +971</option>
                <option value="+65">🇸🇬 +65</option>
              </select>
              <input type="tel" value={phone} onChange={e => { setPhone(e.target.value); setErrors(p => ({...p, phone:''})) }}
                placeholder="9XX XXX XXXX"
                style={{ ...inputStyle(!!phone), flex: 1, padding: '0 16px', borderColor: errors.phone ? 'rgba(248,113,113,0.5)' : (phone ? 'rgba(59,143,232,0.35)' : 'rgba(255,255,255,0.11)') }} />
            </div>
            {errors.phone && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.phone}</div>}
          </div>

          {/* Password */}
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Password</label>
            <div style={{ position: 'relative' }}>
              <input type={showPw ? 'text' : 'password'} value={password}
                onChange={e => { setPassword(e.target.value); setErrors(p => ({...p, password:''})) }}
                placeholder="Create a strong password"
                style={{ ...inputStyle(!!password), borderColor: errors.password ? 'rgba(248,113,113,0.5)' : (password ? 'rgba(59,143,232,0.35)' : 'rgba(255,255,255,0.11)'), fontSize: showPw ? 14 : 16, letterSpacing: showPw ? 0 : 3 }} />
              <button aria-label={showPw ? "Hide password" : "Show password"} onClick={() => setShowPw(!showPw)} style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.3)', display: 'flex' }}>
                <EyeIcon open={showPw} />
              </button>
            </div>
            {!password && (
              <div style={{ fontSize: 10.5, color: 'rgba(255,255,255,0.28)', marginTop: 4 }}>
                8+ characters, with upper and lower case, a number and a symbol
              </div>
            )}
            <PasswordRequirements password={password} />
            {errors.password && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.password}</div>}
          </div>

          {/* Confirm Password */}
          <div style={{ marginBottom: 22 }}>
            <label style={labelStyle}>Confirm Password</label>
            <div style={{ position: 'relative' }}>
              <input type={showCpw ? 'text' : 'password'} value={confirmPassword}
                onChange={e => { setConfirmPassword(e.target.value); setErrors(p => ({...p, confirmPassword:''})) }}
                placeholder="Re-enter password"
                style={{ ...inputStyle(!!confirmPassword), borderColor: errors.confirmPassword ? 'rgba(248,113,113,0.5)' : (confirmPassword ? 'rgba(59,143,232,0.35)' : 'rgba(255,255,255,0.11)'), fontSize: showCpw ? 14 : 16, letterSpacing: showCpw ? 0 : 3 }} />
              <button aria-label={showCpw ? "Hide confirmed password" : "Show confirmed password"} onClick={() => setShowCpw(!showCpw)} style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.3)', display: 'flex' }}>
                <EyeIcon open={showCpw} />
              </button>
            </div>
            {errors.confirmPassword && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.confirmPassword}</div>}
          </div>

          {/* Continue button */}
          <button onClick={handleContinue} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: '100%', height: 50, borderRadius: 14, border: 'none',
            background: 'linear-gradient(135deg, #3B8FE8, #1D65C4)',
            boxShadow: '0 4px 20px rgba(59,143,232,0.3)',
            fontSize: 14, fontWeight: 700, color: '#fff', cursor: 'pointer', marginBottom: 16,
          }}>
            Continue →
          </button>

          <div style={{ textAlign: 'center', fontSize: 13, color: 'rgba(255,255,255,0.32)' }}>
            Have an account?{' '}
            <span onClick={() => navigate('/onboarding/login')} style={{ color: '#F7A97C', fontWeight: 600, cursor: 'pointer' }}>
              Sign in
            </span>
          </div>
        </div>
      </div>
      <style>{`
        input::placeholder { color: rgba(255,255,255,0.22); }
        input:focus { border-color: rgba(59,143,232,0.55) !important; box-shadow: 0 0 0 3px rgba(59,143,232,0.12) !important; outline: none !important; }
        select option { background: #0C1E52; }
      `}</style>
    </div>
  )
}