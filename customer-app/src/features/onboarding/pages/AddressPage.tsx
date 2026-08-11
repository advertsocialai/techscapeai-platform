import { useState, useRef, useEffect, useCallback } from 'react'
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

// ── Country select options — extend as needed. Google's short_name (ISO 3166-1
// alpha-2) is what we map Places results onto, so keys here must match those. ──
const COUNTRIES: Record<string, string> = {
  IN: '🇮🇳 India', US: '🇺🇸 United States', GB: '🇬🇧 United Kingdom',
  AE: '🇦🇪 UAE', SG: '🇸🇬 Singapore', AU: '🇦🇺 Australia', CA: '🇨🇦 Canada',
}

// ── Dynamically load the Google Maps JS API (places library) once. ──
let placesLoadPromise: Promise<void> | null = null
function loadGooglePlaces(apiKey: string): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve()
  if ((window as any).google?.maps?.places) return Promise.resolve()
  if (placesLoadPromise) return placesLoadPromise

  placesLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places`
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Google Maps script'))
    document.head.appendChild(script)
  })
  return placesLoadPromise
}

function getComponent(components: google.maps.GeocoderAddressComponent[], type: string, short = false) {
  const match = components.find(c => c.types.includes(type))
  return match ? (short ? match.short_name : match.long_name) : ''
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

  // Tracks which fields were just auto-filled by Places, so we can show a
  // hint and clear it the moment the user edits that field by hand.
  const [autoFilled, setAutoFilled] = useState<Record<string, boolean>>({})
  const [placesReady, setPlacesReady] = useState(false)
  const [pincodeLoading, setPincodeLoading] = useState(false)

  const streetInputRef = useRef<HTMLInputElement>(null)
  const autocompleteRef = useRef<google.maps.places.Autocomplete | null>(null)

  const apiKey = (import.meta as any).env?.VITE_GOOGLE_PLACES_API_KEY as string | undefined

  // ── Wire up Places Autocomplete on the street address field ──
  useEffect(() => {
    if (!apiKey || !streetInputRef.current) return

    let cancelled = false
    loadGooglePlaces(apiKey)
      .then(() => {
        if (cancelled || !streetInputRef.current) return
        const autocomplete = new google.maps.places.Autocomplete(streetInputRef.current, {
          types: ['address'],
          fields: ['address_components', 'formatted_address'],
        })
        autocomplete.addListener('place_changed', () => {
          const place = autocomplete.getPlace()
          const components = place.address_components
          if (!components) return

          const streetNumber = getComponent(components, 'street_number')
          const route = getComponent(components, 'route')
          const locality = getComponent(components, 'locality') || getComponent(components, 'postal_town')
          const admin1 = getComponent(components, 'administrative_area_level_1')
          const postal = getComponent(components, 'postal_code')
          const countryShort = getComponent(components, 'country', true)

          const street = [streetNumber, route].filter(Boolean).join(' ')
          if (street) setStreetAddress(street)
          if (locality) setCity(locality)
          if (admin1) setState(admin1)
          if (postal) setPostalCode(postal)
          if (countryShort && COUNTRIES[countryShort]) setCountry(countryShort)

          setAutoFilled({
            streetAddress: !!street, city: !!locality, state: !!admin1,
            postalCode: !!postal, country: !!countryShort && !!COUNTRIES[countryShort],
          })
          setErrors({})
        })
        autocompleteRef.current = autocomplete
        setPlacesReady(true)
      })
      .catch(() => setPlacesReady(false))

    return () => { cancelled = true }
  }, [apiKey])

  // ── Optional: auto-fill city/state from a manually-typed Indian PIN code,
  // using the same Places API (Geocoding endpoint) as a fallback lookup. ──
  const lookupByPincode = useCallback(async (pin: string) => {
    if (!apiKey || country !== 'IN' || !/^[1-9][0-9]{5}$/.test(pin)) return
    setPincodeLoading(true)
    try {
      const res = await fetch(
        `https://maps.googleapis.com/maps/api/geocode/json?address=${pin}&components=country:IN&key=${apiKey}`
      )
      const data = await res.json()
      const components = data.results?.[0]?.address_components
      if (components) {
        const locality = getComponent(components, 'locality')
        const admin1 = getComponent(components, 'administrative_area_level_1')
        if (locality) { setCity(locality); setAutoFilled(p => ({ ...p, city: true })) }
        if (admin1) { setState(admin1); setAutoFilled(p => ({ ...p, state: true })) }
      }
    } catch {
      // Silent — pincode lookup is a nice-to-have, never block manual entry
    } finally {
      setPincodeLoading(false)
    }
  }, [apiKey, country])

  function clearAutoFilled(field: string) {
    setAutoFilled(p => (p[field] ? { ...p, [field]: false } : p))
  }

  function validate() {
    const e: Record<string, string> = {}

    if (!streetAddress.trim()) {
      e.streetAddress = 'Street address is required'
    } else if (streetAddress.trim().length < 5 || !/[a-zA-Z]/.test(streetAddress)) {
      e.streetAddress = 'Enter a complete street address'
    }

    if (!city.trim()) {
      e.city = 'City is required'
    } else if (!/^[a-zA-Z\s'.-]{2,}$/.test(city.trim())) {
      e.city = 'Enter a valid city name'
    }

    if (!state.trim()) {
      e.state = 'State is required'
    } else if (!/^[a-zA-Z\s'.-]{2,}$/.test(state.trim())) {
      e.state = 'Enter a valid state name'
    }

    if (!postalCode.trim()) {
      e.postalCode = 'Postal code is required'
    } else if (country === 'IN') {
      if (!/^[1-9][0-9]{5}$/.test(postalCode.trim())) {
        e.postalCode = 'Enter a valid 6-digit Indian PIN code'
      }
    } else if (country === 'US') {
      if (!/^\d{5}(-\d{4})?$/.test(postalCode.trim())) {
        e.postalCode = 'Enter a valid US ZIP code'
      }
    } else if (country === 'GB') {
      if (!/^[A-Za-z]{1,2}\d[A-Za-z\d]?\s?\d[A-Za-z]{2}$/.test(postalCode.trim())) {
        e.postalCode = 'Enter a valid UK postcode (e.g. SW1A 1AA)'
      }
    } else if (country === 'SG') {
      if (!/^\d{6}$/.test(postalCode.trim())) {
        e.postalCode = 'Enter a valid 6-digit Singapore postal code'
      }
    } else if (country === 'AE') {
      // UAE has no formal postal code system — accept any non-empty value
    }

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
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.42)', marginBottom: placesReady ? 6 : 22 }}>
            Step 2 of 4 — Address Details
          </div>
          {placesReady && (
            <div style={{ fontSize: 11, color: 'rgba(59,143,232,0.75)', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 5 }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><circle cx="12" cy="10" r="3"/><path d="M12 21s7-6.5 7-11.5A7 7 0 0 0 5 9.5C5 14.5 12 21 12 21z"/></svg>
              Start typing your address — we'll fill in the rest
            </div>
          )}

          {/* Street Address */}
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Street Address</label>
            <input
              ref={streetInputRef}
              type="text" value={streetAddress}
              onChange={e => { setStreetAddress(e.target.value); clearAutoFilled('streetAddress'); setErrors(p => ({...p, streetAddress: ''})) }}
              placeholder={placesReady ? 'Start typing to search…' : '123 Main Street'}
              style={inputStyle(!!streetAddress, !!errors.streetAddress)}
            />
            {errors.streetAddress && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.streetAddress}</div>}
          </div>

          {/* City + State grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 0 }}>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>City {autoFilled.city && <AutoTag />}</label>
              <input
                type="text" value={city}
                onChange={e => { setCity(e.target.value); clearAutoFilled('city'); setErrors(p => ({...p, city: ''})) }}
                placeholder="St. Louis"
                style={inputStyle(!!city, !!errors.city)}
              />
              {errors.city && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.city}</div>}
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>State {autoFilled.state && <AutoTag />}</label>
              <input
                type="text" value={state}
                onChange={e => { setState(e.target.value); clearAutoFilled('state'); setErrors(p => ({...p, state: ''})) }}
                placeholder="Missouri"
                style={inputStyle(!!state, !!errors.state)}
              />
              {errors.state && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.state}</div>}
            </div>
          </div>

          {/* Postal + Country grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 0 }}>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Postal Code {autoFilled.postalCode && <AutoTag />}</label>
              <input
                type="text" value={postalCode}
                onChange={e => { setPostalCode(e.target.value); clearAutoFilled('postalCode'); setErrors(p => ({...p, postalCode: ''})) }}
                onBlur={e => lookupByPincode(e.target.value.trim())}
                placeholder="63101"
                style={inputStyle(!!postalCode, !!errors.postalCode)}
              />
              {pincodeLoading && <div style={{ fontSize: 10.5, color: 'rgba(59,143,232,0.7)', marginTop: 4 }}>Looking up city & state…</div>}
              {errors.postalCode && <div style={{ fontSize: 11, color: '#F87171', marginTop: 4 }}>{errors.postalCode}</div>}
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Country {autoFilled.country && <AutoTag />}</label>
              <select
                value={country}
                onChange={e => { setCountry(e.target.value); clearAutoFilled('country'); setErrors(p => ({...p, country: ''})) }}
                style={{
                  ...inputStyle(!!country, !!errors.country),
                  padding: '0 12px',
                  cursor: 'pointer',
                  appearance: 'none',
                }}
              >
                {Object.entries(COUNTRIES).map(([code, label]) => (
                  <option key={code} value={code}>{label}</option>
                ))}
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
        .pac-container { border-radius: 13px !important; margin-top: 4px; background: #0C1E52 !important; border: 1px solid rgba(59,143,232,0.35) !important; box-shadow: 0 12px 32px rgba(0,0,0,0.4) !important; overflow: hidden; }
        .pac-item { background: transparent !important; border-color: rgba(255,255,255,0.06) !important; color: rgba(255,255,255,0.75) !important; padding: 9px 12px !important; }
        .pac-item:hover { background: rgba(59,143,232,0.1) !important; }
        .pac-item-query { color: #fff !important; }
        .pac-matched { color: #3B8FE8 !important; }
        .pac-icon { display: none !important; }
      `}</style>
    </div>
  )
}

function AutoTag() {
  return (
    <span style={{ color: 'rgba(59,143,232,0.75)', fontSize: 8.5, letterSpacing: 0, textTransform: 'none', fontWeight: 600 }}>
      · auto-filled
    </span>
  )
}
