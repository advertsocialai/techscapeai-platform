import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOnboarding } from '../context/OnboardingContext'

function BackArrow() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
      <polyline points="15,18 9,12 15,6"/>
    </svg>
  )
}

const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 9.5, fontWeight: 700,
  color: 'rgba(255,255,255,0.28)', letterSpacing: 0.9,
  textTransform: 'uppercase', marginBottom: 6,
}

function inputStyle(hasValue: boolean, hasError = false): React.CSSProperties {
  return {
    width: '100%', height: 50,
    background: hasError ? 'rgba(248,113,113,0.06)' : hasValue ? 'rgba(59,143,232,0.06)' : 'rgba(255,255,255,0.07)',
    border: `1px solid ${hasError ? 'rgba(248,113,113,0.5)' : hasValue ? 'rgba(59,143,232,0.35)' : 'rgba(255,255,255,0.11)'}`,
    borderRadius: 13, padding: '0 16px',
    fontSize: 14, color: '#fff', outline: 'none',
    transition: 'all 0.18s',
  }
}

export default function AddressPage() {
  const navigate = useNavigate()
  const { setAddress } = useOnboarding()

  const [streetAddress, setStreetAddress] = useState('')
  const [city, setCity] = useState('')
  const [state, setState] = useState('')
  const [postalCode, setPostalCode] = useState('')
  const [country, setCountry] = useState('IN')
  const [company, setCompany] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  function validate() {
    const e: Record<string, string> = {}
    if (!streetAddress.trim()) e.streetAddress = 'Street address is required'
    if (!city.trim()) e.city = 'City is required'
    if (!state.trim()) e.state = 'State is required'
    if (!postalCode.trim()) e.postalCode = 'Postal code is required'
    if (!country) e.country = 'Country is required'
    return e
  }

  function handleContinue() {
    const e = validate()
    if (Object.keys(e).length > 0) { setErrors(e); return }
    setAddress({ streetAddress, city, state, postalCode, country, company })
    navigate('/onboarding/otp')
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '32px 20px 40px' }}>
      <div style={{ width: '100%', maxWidth: 430, position: 'relative', zIndex: 1 }}>

        {/* Back nav */}
        <div onClick={() => navigate('/onboarding/personal-info')} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 20, cursor: 'pointer', color: 'rgba(255,255,255,0.45)', fontSize: 13, fontWeight: 500 }}>
          <BackArrow /> Personal Info
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
              <div key={i} style={{
                flex: 1, height: 3, borderRadius: 2,
                background: i === 0 ? '#F7A97C' : i === 1 ? '#3B8FE8' : 'rgba(255,255,255,0.1)'
              }} />
            ))}
          </div>

          <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', letterSpacing: -0.3, marginBottom: 4 }}>
            Plan less. Experience more. ✈️
          </div>
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.42)', marginBottom: 22 }}>
            Step 2 of 4 — Address Details
          </div>

          {/* Street Address */}
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Street Address</label>
            <input
              type="text" value={streetAddress}
              onChange={e => { setStreetAddress(e.target.value); setErrors(p => ({...p, streetAddress: ''})) }}
              placeholder="123 Main Street"
              style={inputStyle(!!streetAddress, !!errors.streetAddress)}
            />
            {errors.streetAddress && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.streetAddress}</div>}
          </div>

          {/* City + State grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 0 }}>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>City</label>
              <input
                type="text" value={city}
                onChange={e => { setCity(e.target.value); setErrors(p => ({...p, city: ''})) }}
                placeholder="St. Louis"
                style={inputStyle(!!city, !!errors.city)}
              />
              {errors.city && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.city}</div>}
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>State</label>
              <input
                type="text" value={state}
                onChange={e => { setState(e.target.value); setErrors(p => ({...p, state: ''})) }}
                placeholder="Missouri"
                style={inputStyle(!!state, !!errors.state)}
              />
              {errors.state && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.state}</div>}
            </div>
          </div>

          {/* Postal + Country grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 0 }}>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Postal Code</label>
              <input
                type="text" value={postalCode}
                onChange={e => { setPostalCode(e.target.value); setErrors(p => ({...p, postalCode: ''})) }}
                placeholder="63101"
                style={inputStyle(!!postalCode, !!errors.postalCode)}
              />
              {errors.postalCode && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.postalCode}</div>}
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Country</label>
              <select
                value={country}
                onChange={e => { setCountry(e.target.value); setErrors(p => ({...p, country: ''})) }}
                style={{
                  ...inputStyle(!!country, !!errors.country),
                  padding: '0 12px',
                  cursor: 'pointer',
                  appearance: 'none',
                }}
              >
                <option value="IN">🇮🇳 India</option>
                <option value="US">🇺🇸 United States</option>
                <option value="GB">🇬🇧 United Kingdom</option>
                <option value="AE">🇦🇪 UAE</option>
                <option value="SG">🇸🇬 Singapore</option>
                <option value="AU">🇦🇺 Australia</option>
                <option value="CA">🇨🇦 Canada</option>
              </select>
            </div>
          </div>

          {/* Company — optional */}
          <div style={{ marginBottom: 22 }}>
            <label style={labelStyle}>
              Company{' '}
              <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: 9, letterSpacing: 0, textTransform: 'none', fontWeight: 400 }}>
                optional
              </span>
            </label>
            <input
              type="text" value={company}
              onChange={e => setCompany(e.target.value)}
              placeholder="Your company name"
              style={inputStyle(!!company)}
            />
          </div>

          {/* Continue */}
          <button onClick={handleContinue} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: '100%', height: 50, borderRadius: 14, border: 'none',
            background: 'linear-gradient(135deg, #3B8FE8, #1D65C4)',
            boxShadow: '0 4px 20px rgba(59,143,232,0.3)',
            fontSize: 14, fontWeight: 700, color: '#fff', cursor: 'pointer', marginBottom: 10,
          }}>
            Continue →
          </button>

          {/* Back */}
          <button onClick={() => navigate('/onboarding/personal-info')} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: '100%', height: 50, borderRadius: 14,
            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
            fontSize: 13, fontWeight: 600, color: 'rgba(255,255,255,0.5)', cursor: 'pointer',
          }}>
            ← Back
          </button>
        </div>
      </div>
      <style>{`
        input::placeholder { color: rgba(255,255,255,0.22); }
        input:focus, select:focus { border-color: rgba(59,143,232,0.55) !important; box-shadow: 0 0 0 3px rgba(59,143,232,0.12) !important; outline: none !important; }
        select option { background: #0C1E52; color: #fff; }
      `}</style>
    </div>
  )
}