import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { OnboardingProvider } from './features/onboarding/context/OnboardingContext'

// Pages — we'll create these next
import LoginPage from './features/onboarding/pages/LoginPage'
import PersonalInfoPage from './features/onboarding/pages/PersonalInfoPage'
import AddressPage from './features/onboarding/pages/AddressPage'
import OtpPage from './features/onboarding/pages/OtpPage'
import TermsPage from './features/onboarding/pages/TermsPage'
import SuccessPage from './features/onboarding/pages/SuccessPage'

// Dashboard placeholder
function DashboardPlaceholder() {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: 'Outfit, sans-serif',
      color: '#fff',
      fontSize: '20px'
    }}>
      🚀 Dashboard coming soon...
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <OnboardingProvider>
        <Routes>
          {/* Redirect root to login */}
          <Route path="/" element={<Navigate to="/onboarding/login" replace />} />

          {/* Onboarding flow — Screens 1-6 */}
          <Route path="/onboarding/login"        element={<LoginPage />} />
          <Route path="/onboarding/personal-info" element={<PersonalInfoPage />} />
          <Route path="/onboarding/address"       element={<AddressPage />} />
          <Route path="/onboarding/otp"           element={<OtpPage />} />
          <Route path="/onboarding/terms"         element={<TermsPage />} />
          <Route path="/onboarding/success"       element={<SuccessPage />} />

          {/* Dashboard placeholder */}
          <Route path="/dashboard" element={<DashboardPlaceholder />} />

          {/* Catch all */}
          <Route path="*" element={<Navigate to="/onboarding/login" replace />} />
        </Routes>
      </OnboardingProvider>
    </BrowserRouter>
  )
}