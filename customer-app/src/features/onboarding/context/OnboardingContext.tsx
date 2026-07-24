import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
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
      return saved ? { ...defaultState, ...JSON.parse(saved) } : defaultState
    } catch {
      return defaultState
    }
  })

  useEffect(() => {
    localStorage.setItem('klara_onboarding_state', JSON.stringify(state))
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

export function useOnboarding() {
  const ctx = useContext(OnboardingContext)
  if (!ctx) throw new Error('useOnboarding must be used within OnboardingProvider')
  return ctx
}