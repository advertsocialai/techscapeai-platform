import { createContext, useContext, useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import type { PersonalInfoData, AddressData, TermsData } from '../../../types/auth'

interface OnboardingState {
  // Screen 2 — Personal Info
  firstName: string
  lastName: string
  email: string
  phone: string
  countryCode: string
  password: string

  // Screen 3 — Address
  streetAddress: string
  city: string
  state: string
  postalCode: string
  country: string
  company: string

  // Screen 4 — OTP
  otpVerified: boolean

  // Screen 5 — Terms
  termsAccepted: boolean
  ageConfirmed: boolean
  marketingOptIn: boolean
}

interface OnboardingContextType extends OnboardingState {
  setPersonalInfo: (data: PersonalInfoData) => void
  setAddress: (data: AddressData) => void
  setOtpVerified: (v: boolean) => void
  setTerms: (data: TermsData) => void
  reset: () => void
}

const defaultState: OnboardingState = {
  firstName: '',
  lastName: '',
  email: '',
  phone: '',
  countryCode: '+91',
  password: '',
  streetAddress: '',
  city: '',
  state: '',
  postalCode: '',
  country: 'IN',
  company: '',
  otpVerified: false,
  termsAccepted: false,
  ageConfirmed: false,
  marketingOptIn: false,
}

const OnboardingContext = createContext<OnboardingContextType | null>(null)

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<OnboardingState>(() => {
    try {
      const saved = localStorage.getItem('klara_onboarding_state')
      // `password` is deliberately dropped on restore. Nothing writes it any
      // more (see the effect below), and forcing it empty here also discards
      // cleartext left in storage by a build from before that change.
      return saved ? { ...defaultState, ...JSON.parse(saved), password: '' } : defaultState
    } catch {
      return defaultState
    }
  })

  useEffect(() => {
    // SEC-1: this used to persist the whole state object verbatim, which put the
    // signup password in cleartext in localStorage — readable by any script on
    // the origin, and left behind on shared or kiosk machines after signup. The
    // password now lives in React state for the length of the wizard and never
    // reaches disk. Writing '' rather than omitting the key also overwrites any
    // password a previous build already stored.
    //
    // A reload mid-wizard therefore loses it. That is handled, not ignored:
    // RequireStep treats a missing password as missing identity and sends the
    // user back to /onboarding/personal-info.
    localStorage.setItem('klara_onboarding_state', JSON.stringify({ ...state, password: '' }))
  }, [state])

  const setPersonalInfo = (data: PersonalInfoData) => {
    setState(prev => ({ ...prev, ...data }))
  }

  const setAddress = (data: AddressData) => {
    setState(prev => ({ ...prev, ...data }))
  }

  const setOtpVerified = (v: boolean) => {
    setState(prev => ({ ...prev, otpVerified: v }))
  }

  const setTerms = (data: TermsData) => {
    setState(prev => ({ ...prev, ...data }))
  }

  const reset = () => {
    setState(defaultState)
    localStorage.removeItem('klara_onboarding_state')
  }

  return (
    <OnboardingContext.Provider value={{ ...state, setPersonalInfo, setAddress, setOtpVerified, setTerms, reset }}>
      {children}
    </OnboardingContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components -- hook is colocated with its provider by design
export function useOnboarding() {
  const ctx = useContext(OnboardingContext)
  if (!ctx) throw new Error('useOnboarding must be used within OnboardingProvider')
  return ctx
}