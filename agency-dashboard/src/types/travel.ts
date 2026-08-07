// Mirrors api/app/schemas/travel.py response shapes exactly.

export type LeadSource = 'whatsapp' | 'website' | 'phone' | 'franchisee' | 'referral' | 'sms' | 'email' | 'other'
export type LeadQualification = 'cold' | 'warm' | 'hot' | 'converted' | 'lost'
export type LeadStatus = 'new' | 'qualified' | 'itinerary_sent' | 'negotiating' | 'booked' | 'lost'

export interface Lead {
  id: string
  business_id: string
  customer_id: string | null
  source: LeadSource
  raw_message: string
  intent: string | null
  destination_hint: string | null
  pax_count: number | null
  budget_inr: number | null
  duration_days: number | null
  score: number
  qualification: LeadQualification
  status: LeadStatus
  itinerary_id: string | null
  franchisee_id: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export type BookingStatus = 'confirmed' | 'in_progress' | 'completed' | 'cancelled'
export type BookingVisaState = 'not_required' | 'pending' | 'submitted' | 'approved' | 'rejected'

export interface Booking {
  id: string
  business_id: string
  booking_ref: string
  customer_id: string | null
  itinerary_id: string | null
  destination: string | null
  trip_type: string | null
  departure_date: string | null
  return_date: string | null
  pax_count: number
  grand_total_inr: number
  deposit_inr: number
  balance_inr: number
  balance_due_date: string | null
  visa_status: BookingVisaState
  status: BookingStatus
  coordinator_name: string | null
  coordinator_phone: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export interface CustomerProfile {
  id: string
  business_id: string
  full_name: string | null
  email: string | null
  phone: string | null
  preferences: Record<string, unknown>
  family_profile: Record<string, unknown>
  language: string
  notes: string | null
  past_trips: Record<string, unknown>[]
  last_intent: string | null
  created_at: string
  updated_at: string
}

export interface PlaybookSummary {
  id: string
  title: string
  category: string
  priority: string
  sla: string
  channels: string[]
  trigger: string
}

export interface PlaybookRun {
  id: string
  business_id: string
  use_case_id: string
  booking_id: string | null
  customer_id: string | null
  lead_id: string | null
  incident_id: string | null
  trigger_kind: 'manual' | 'schedule' | 'event' | 'webhook'
  channels: string[]
  status: 'sent' | 'failed' | 'partial' | 'skipped' | 'queued'
  rendered: Record<string, unknown>
  delivery: Record<string, unknown>
  error_message: string | null
  created_at: string
}
