/**
 * Traveller-facing data layer — CURRENTLY ALL STUBBED.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * READ THIS BEFORE USING ANY OF IT
 *
 * Not one of these endpoints exists on the backend. Every function below
 * returns a hardcoded fixture. This module exists so the traveller screens can
 * be built and reviewed now, and so switching to real data later is a change to
 * THIS FILE ONLY — the screens never learn that they were stubbed.
 *
 * Two open questions make real implementation impossible today, and neither is
 * an engineering problem:
 *
 *   B-FE7-01 — is customer-app for TRAVELLERS or for AGENCIES self-serving?
 *     The existing onboarding flow collects business_name/industry and calls
 *     /auth/register-business, which is an agency signing up. These screens
 *     assume traveller. If that assumption is wrong, delete this file.
 *
 *   B-FE7-02 — the backend has NO TRAVELLER IDENTITY. Every ts_users row
 *     belongs to a business and every JWT carries business_id; a traveller is a
 *     travel_customers row with no password and no token. So there is currently
 *     nothing to authenticate a traveller against, and no scoping rule that
 *     would let one safely read their own booking.
 *
 * WHY STUB RATHER THAN CALL SOMETHING CLOSE: the agency endpoints DO hold this
 * data (travel_bookings, payment_links), but they are business-scoped. Pointing
 * a traveller screen at them would either 401, or — far worse, if a traveller
 * token were ever minted carelessly — return other customers' bookings. A
 * fixture cannot leak anything.
 *
 * WHEN THE BACKEND EXISTS: replace each body with its real call. The signatures
 * are deliberately shaped like the endpoints that ought to exist, and each one
 * names its expected route below.
 * ───────────────────────────────────────────────────────────────────────── */

/** Flipped to false once the real endpoints land. Screens branch on it to show
 *  the stub banner — nothing else should depend on it. */
export const TRAVELLER_API_IS_STUBBED = true

export const STUB_NOTICE =
  'Sample data. These screens have no backend yet — traveller endpoints and traveller ' +
  'authentication both remain to be built (B-FE7-01, B-FE7-02). Nothing here reflects a real booking.'

/* ── Types (the shapes the real endpoints should return) ─────────────────── */

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

/* ── Fixtures ────────────────────────────────────────────────────────────── */

// Fixed values, not randomised: a screenshot taken today should match one taken
// tomorrow, and a reviewer should be able to spot "this is the fixture" instantly.
const TRIP: Trip = {
  booking_ref: 'SAMPLE-GG-00000',
  destination: 'Bali, Indonesia',
  status: 'confirmed',
  start_date: '2026-11-14',
  end_date: '2026-11-21',
  pax: 2,
  agency_name: 'GoGaga Holidays',
  agent_name: 'Sample Agent',
  total_amount: '184000',
  currency: 'INR',
  amount_paid: '50000',
  visa_state: 'pending',
  itinerary: [
    { day: 1, title: 'Arrive in Denpasar', detail: 'Airport pickup and transfer to Seminyak. Evening free.' },
    { day: 2, title: 'Seminyak & Tanah Lot', detail: 'Beach morning, sunset at Tanah Lot temple.' },
    { day: 3, title: 'Ubud day trip', detail: 'Rice terraces, monkey forest, art market.' },
    { day: 4, title: 'Nusa Penida', detail: 'Fast boat, Kelingking Beach, snorkelling at Crystal Bay.' },
    { day: 5, title: 'Free day', detail: 'Optional spa or cooking class.' },
    { day: 6, title: 'Uluwatu', detail: 'Cliff temple and Kecak fire dance at sunset.' },
    { day: 7, title: 'Departure', detail: 'Transfer to Denpasar airport.' },
  ],
}

const PAYMENTS: TravellerPayment[] = [
  {
    id: 'sample-1',
    description: 'Booking deposit',
    amount: '50000',
    currency: 'INR',
    status: 'paid',
    due_at: null,
    pay_url: null,
  },
  {
    id: 'sample-2',
    description: 'Balance payment',
    amount: '134000',
    currency: 'INR',
    status: 'sent',
    due_at: '2026-10-14T00:00:00Z',
    // Deliberately a stub:// URL — mirrors what the backend returns without
    // Razorpay credentials, so the screen has to handle the un-openable case.
    pay_url: 'stub://payment-link/sample-2',
  },
]

const MESSAGES: TravellerMessage[] = [
  { id: 'm1', from: 'agency', text: 'Hi! Your Bali itinerary is confirmed. Visa docs needed by 20 Oct.', at: '2026-08-06T09:12:00Z' },
  { id: 'm2', from: 'you', text: 'Thanks! Can we add a day in Ubud?', at: '2026-08-06T10:04:00Z' },
  { id: 'm3', from: 'agency', text: "Checking availability — I'll confirm by tomorrow.", at: '2026-08-06T10:31:00Z' },
]

/** Small delay so loading states are actually exercised in review, rather than
 *  resolving instantly and hiding a missing skeleton. */
function settle<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), 350))
}

export const travellerApi = {
  /** Real route would be roughly: GET /travel/v1/me/trip */
  trip: () => settle(TRIP),

  /** Real route: GET /travel/v1/me/payments */
  payments: () => settle(PAYMENTS),

  /** Real route: GET /travel/v1/me/messages */
  messages: () => settle(MESSAGES),

  /**
   * Real route: POST /travel/v1/me/messages
   *
   * 💬 Deliberately does NOT send anything, and says so rather than echoing a
   * fake success. There is no traveller→agency inbound channel at all — the
   * WhatsApp integration is outbound-only, which is also why the 24-hour
   * session window is tracked in an in-process dict (DEBT-10). Pretending a
   * message was delivered is exactly the failure this codebase keeps guarding
   * against.
   */
  sendMessage: async (): Promise<never> => {
    throw new Error(
      'Messaging is not wired. There is no traveller-to-agency inbound channel on the backend yet.',
    )
  },
}
