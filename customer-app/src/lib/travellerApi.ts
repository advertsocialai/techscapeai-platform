/**
 * Traveller-facing data layer — NOW REAL.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * This file used to return hardcoded fixtures, because none of these
 * endpoints existed (B-FE7-03). They exist now:
 *
 *     POST /travel/v1/me/auth/request-otp
 *     POST /travel/v1/me/auth/verify-otp
 *     GET  /travel/v1/me/trip
 *     GET  /travel/v1/me/payments
 *     GET  /travel/v1/me/messages
 *
 * The screens never learned they were stubbed, which was the whole point of
 * routing everything through this one module — swapping to real data is a
 * change to THIS FILE ONLY. The exported shapes are unchanged.
 *
 * A TRAVELLER TOKEN IS NOT AN AGENCY TOKEN
 * ----------------------------------------
 * It is stored under a DIFFERENT key (`klara_traveller_token`) and sent by a
 * DIFFERENT axios instance than `lib/api.ts`. That separation is deliberate:
 * the backend refuses each token family on the other's endpoints, and mixing
 * them client-side would turn a clean 401 into a confusing one.
 *
 * There is no traveller refresh token by design — the backend issues a
 * short-lived (60 min) token and no refresh. When it expires the traveller
 * requests a new OTP. So this module must NOT try to refresh; on 401 it clears
 * the token and lets the screen ask for a code again.
 * ───────────────────────────────────────────────────────────────────────── */
import axios from 'axios'

/** Kept exported so screens can keep branching on it; now false. */
export const TRAVELLER_API_IS_STUBBED = false

export const STUB_NOTICE = ''

const TOKEN_KEY = 'klara_traveller_token'

export function getTravellerToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setTravellerToken(t: string) {
  localStorage.setItem(TOKEN_KEY, t)
}
export function clearTravellerToken() {
  localStorage.removeItem(TOKEN_KEY)
}
export function isTravellerAuthenticated(): boolean {
  return !!getTravellerToken()
}

// Separate instance from lib/api.ts on purpose — different base path, and a
// different token family that must never be attached to agency calls.
const travellerHttp = axios.create({
  baseURL: import.meta.env.VITE_TRAVEL_API_URL || '/api/travel/v1/me',
  headers: { 'Content-Type': 'application/json' },
})

travellerHttp.interceptors.request.use((config) => {
  const t = getTravellerToken()
  if (t) config.headers.Authorization = `Bearer ${t}`
  return config
})

travellerHttp.interceptors.response.use(
  (r) => r,
  (err) => {
    // No refresh attempt: there is no traveller refresh token to attempt one
    // with. Clearing here means the next render sees an unauthenticated
    // traveller and asks for a code, rather than looping on a dead token.
    if (err?.response?.status === 401) clearTravellerToken()
    return Promise.reject(err)
  },
)

/* ── Types (unchanged — the screens depend on these) ─────────────────────── */

export interface TripDay {
  day: number
  title: string
  detail: string
}

export interface Trip {
  booking_ref: string
  destination: string
  status: 'confirmed' | 'in_progress' | 'completed' | 'cancelled'
  start_date: string
  end_date: string
  pax: number
  agency_name: string
  agent_name: string | null
  itinerary: TripDay[]
  /** Major units. Currency is a sibling field and must always be shown with it. */
  total_amount: string
  currency: string
  amount_paid: string
  visa_state: 'not_required' | 'pending' | 'submitted' | 'approved' | 'rejected'
}

export interface TravellerPayment {
  id: string
  description: string
  amount: string
  currency: string
  status: 'created' | 'sent' | 'viewed' | 'paid' | 'expired'
  due_at: string | null
  /** A `stub://` URL is NOT openable — screens must not render it as a link. */
  pay_url: string | null
}

export interface TravellerMessage {
  id: string
  from: 'agency' | 'you'
  text: string
  at: string
}

/* ── API ─────────────────────────────────────────────────────────────────── */

export const travellerApi = {
  /** Always resolves, even for an unknown address — the backend will not say
   *  whether the email belongs to a customer, and neither should the UI. */
  requestOtp: (email: string) =>
    travellerHttp.post('/auth/request-otp', { email }).then((r) => r.data),

  verifyOtp: async (email: string, code: string) => {
    const { data } = await travellerHttp.post<{ access_token: string }>(
      '/auth/verify-otp',
      { email, code },
    )
    setTravellerToken(data.access_token)
    return data
  },

  trip: () => travellerHttp.get<Trip>('/trip').then((r) => r.data),

  payments: () => travellerHttp.get<TravellerPayment[]>('/payments').then((r) => r.data),

  messages: () => travellerHttp.get<TravellerMessage[]>('/messages').then((r) => r.data),

  /**
   * 💬 STILL NOT WIRED, and still throws rather than faking success.
   *
   * This is not an oversight — there is no traveller→agency inbound channel on
   * the backend, so there is deliberately no POST /me/messages to call. The
   * WhatsApp integration is outbound-only. Accepting text here and letting it
   * vanish would be worse than saying so: a customer who believes they reported
   * a visa problem, and did not, is worse off than one who was told the channel
   * is unavailable.
   */
  sendMessage: async (): Promise<never> => {
    throw new Error(
      'Messaging is not wired. There is no traveller-to-agency inbound channel on the backend yet.',
    )
  },
}
