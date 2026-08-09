import { Navigate } from 'react-router-dom'
import { useOnboarding } from './context/OnboardingContext'

/**
 * Step ordering for the signup wizard.
 *
 * `otpVerified` was being WRITTEN by OtpPage and read by nothing at all — a
 * grep for it returned only its own declaration, default and setter. So the
 * email-verification step was decorative: navigating straight to
 * /onboarding/terms created an account against a never-verified address.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * THIS IS NOT THE GUARANTEE, AND MUST NOT BE DESCRIBED AS ONE.
 *
 * The state behind it lives in localStorage (`klara_onboarding_state`), so
 * anyone can set `otpVerified: true` in devtools and walk past this. It closes
 * the accidental path — a bookmark, a back button, a shared link — not a
 * deliberate one.
 *
 * The real fix belongs on the server: `RegisterBusinessIn` has no OTP field, so
 * the backend never checks that the address was verified, no matter what the
 * client does. Logged as B-FE7-07 in BLOCKERS.md.
 * ───────────────────────────────────────────────────────────────────────── */
type Step = 'address' | 'otp' | 'terms'

export default function RequireStep({
  step,
  children,
}: {
  step: Step
  children: React.ReactNode
}) {
  const { email, password, otpVerified } = useOnboarding()

  // Every step past the first needs the identity captured on screen 1. Without
  // it there is nothing to send an OTP to and nothing to register.
  const hasIdentity = !!email && !!password
  if (!hasIdentity) return <Navigate to="/onboarding/personal-info" replace />

  if (step === 'terms' && !otpVerified) {
    return <Navigate to="/onboarding/otp" replace />
  }

  return <>{children}</>
}
