import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { OnboardingProvider } from './features/onboarding/context/OnboardingContext'

// Onboarding — screens 1-6
import LoginPage from './features/onboarding/pages/LoginPage'
import PersonalInfoPage from './features/onboarding/pages/PersonalInfoPage'
import AddressPage from './features/onboarding/pages/AddressPage'
import OtpPage from './features/onboarding/pages/OtpPage'
import TermsPage from './features/onboarding/pages/TermsPage'
import SuccessPage from './features/onboarding/pages/SuccessPage'

// Traveller app — currently backed by stubs, see lib/travellerApi.ts
import TripShell from './features/trip/TripShell'
import TripPage from './features/trip/TripPage'
import PaymentsPage from './features/trip/PaymentsPage'
import MessagesPage from './features/trip/MessagesPage'

/**
 * `@tanstack/react-query` was already a dependency but had no provider — any
 * useQuery would have thrown at runtime. Wired here.
 *
 * `retry: 1` rather than the default 3: these screens surface an explicit error
 * with a retry button, so silently retrying three times just makes a broken
 * request feel like a slow one.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <OnboardingProvider>
          <Routes>
            <Route path="/" element={<Navigate to="/onboarding/login" replace />} />

            <Route path="/onboarding/login" element={<LoginPage />} />
            <Route path="/onboarding/personal-info" element={<PersonalInfoPage />} />
            <Route path="/onboarding/address" element={<AddressPage />} />
            <Route path="/onboarding/otp" element={<OtpPage />} />
            <Route path="/onboarding/terms" element={<TermsPage />} />
            <Route path="/onboarding/success" element={<SuccessPage />} />

            {/* Traveller surface. No auth guard: there is no traveller identity
                to guard with (B-FE7-02), and a guard that checks an AGENCY token
                would be the wrong check dressed up as security. The screens show
                fixtures only, so there is nothing here to protect. */}
            <Route path="/trip" element={<TripShell />}>
              <Route index element={<TripPage />} />
              <Route path="payments" element={<PaymentsPage />} />
              <Route path="messages" element={<MessagesPage />} />
            </Route>

            {/* The old placeholder route now lands somewhere real. */}
            <Route path="/dashboard" element={<Navigate to="/trip" replace />} />

            <Route path="*" element={<Navigate to="/onboarding/login" replace />} />
          </Routes>
        </OnboardingProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
