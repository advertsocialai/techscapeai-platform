import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { OnboardingProvider } from './features/onboarding/context/OnboardingContext'
import RequireStep from './features/onboarding/RequireStep'
import RequireTraveller from './features/trip/RequireTraveller'
import TravellerLoginPage from './features/trip/TravellerLoginPage'

// Onboarding — screens 1-6
import LoginPage from './features/onboarding/pages/LoginPage'
import GoogleCallbackPage from './features/onboarding/pages/GoogleCallbackPage'
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
            {/* Must match OAUTH_REDIRECT_BASE + "/auth/google/callback" on the
                backend exactly — that's the redirect_uri baked into both the
                consent-screen URL and the code exchange. */}
            <Route path="/auth/google/callback" element={<GoogleCallbackPage />} />
            <Route path="/onboarding/personal-info" element={<PersonalInfoPage />} />
            {/* Steps run in order. `terms` additionally requires a verified OTP
                — see RequireStep for why that check is necessary but not
                sufficient, and which backend gap still has to close. */}
            <Route
              path="/onboarding/address"
              element={<RequireStep step="address"><AddressPage /></RequireStep>}
            />
            <Route
              path="/onboarding/otp"
              element={<RequireStep step="otp"><OtpPage /></RequireStep>}
            />
            <Route
              path="/onboarding/terms"
              element={<RequireStep step="terms"><TermsPage /></RequireStep>}
            />
            <Route path="/onboarding/success" element={<SuccessPage />} />

            {/* Traveller surface. GUARDED as of the switch to real data: a
                traveller identity now exists (POST /travel/v1/me/auth/verify-otp
                issues a traveller-only token), and these screens render a real
                customer's booking rather than fixtures. The guard is the first
                line only — every /me endpoint independently requires that token
                and scopes by customer_id AND business_id. */}
            {/* Traveller sign-in: email -> OTP. Separate from /onboarding/login
                because a traveller has NO password to present. */}
            <Route path="/trip/login" element={<TravellerLoginPage />} />
            <Route path="/trip" element={<RequireTraveller><TripShell /></RequireTraveller>}>
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
