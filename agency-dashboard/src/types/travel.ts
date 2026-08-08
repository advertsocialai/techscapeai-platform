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

// ═══════════════════════════════════════════════════════════════════════════
// Money
// ═══════════════════════════════════════════════════════════════════════════
// The platform is multi-currency (INR + USD/CAD for intl branches). An amount
// is NEVER meaningful on its own — every interface below that carries a value
// carries its currency in the same object, and every helper here forces the
// pair to travel together. Do not add a bare `amount: number` anywhere.
//
// Two representations exist on the wire and they are NOT interchangeable:
//   * `number` — Postgres NUMERIC read straight back through PostgREST
//                (payment_links.amount, report revenue aggregates).
//   * `string` — Python Decimals that the backend str()s on purpose so the
//                JSON encoder can never silently float money
//                (analytics/revenue-rollup, analytics/cost).
// The types preserve whichever one the endpoint actually returns.

/** Amount as a JSON number + its ISO-4217 code. */
export interface Money {
  amount: number
  currency: string
}

/** Amount the backend serialised as a decimal string + its ISO-4217 code. */
export interface DecimalMoney {
  amount: string
  currency: string
}

// ═══════════════════════════════════════════════════════════════════════════
// Calls  (travel_calls — GET /travel/v1/calls/*)
// ═══════════════════════════════════════════════════════════════════════════
export type CallStatus = 'active' | 'completed' | 'failed'
export type CallMode = 'ai' | 'agent' | 'conference'

/** travel_calls.takeover_state. Reached over the WS `takeover_state` event —
 *  see the note on `Call` below. */
export type TakeoverState = 'ai' | 'monitoring' | 'coaching' | 'human'

/**
 * Mirrors `CallOut` in api/app/schemas/travel.py.
 *
 * NOTE: `takeover_state` is a real column on travel_calls but is NOT in the
 * CallOut response model, so it is absent from every REST payload including
 * the four takeover responses. The live takeover state arrives only on the
 * `/ws/calls/{id}` `takeover_state` broadcast — that is the source of truth.
 */
export interface Call {
  id: string
  business_id: string
  lead_id: string | null
  provider_sid: string | null
  status: CallStatus
  mode: CallMode
  duration_sec: number | null
  recording_url: string | null
  sentiment_score: number | null
  stt_engine: string | null
  language: string
  started_at: string | null
  ended_at: string | null
  created_at: string
}

/** Mirrors `TranscriptOut` in api/app/schemas/travel.py. */
export interface TranscriptLine {
  id: string
  call_id: string
  speaker: string
  text_original: string
  text_translated: string | null
  timestamp_ms: number
  sentiment: Record<string, unknown>
  created_at: string
}

/** Values migration 0005 documents for travel_call_events.event_type. The
 *  column is a bare VARCHAR with no CHECK — treat unknown values as valid. */
export type KnownCallEventType =
  | 'takeover_monitor'
  | 'takeover_barge'
  | 'takeover_full'
  | 'takeover_release'
  | 'sentiment_update'
  | 'suggestion_generated'
  | 'post_call_complete'

/** A travel_call_events row (returned raw — no response_model on the route). */
export interface CallEvent {
  id: string
  call_id: string
  /** One of `KnownCallEventType`, but the column is unconstrained. */
  event_type: string
  actor_id: string | null
  payload: Record<string, unknown>
  created_at: string
}

// ═══════════════════════════════════════════════════════════════════════════
// Takeover  (POST /travel/v1/calls/{id}/takeover/*)
// ═══════════════════════════════════════════════════════════════════════════
/** Body for monitor/barge. `full` and `release` take no body. */
export interface TakeoverPayload {
  /** E.164, India only. Omit to use the caller's configured number. */
  supervisor_number?: string | null
}

// ═══════════════════════════════════════════════════════════════════════════
// Packages  (travel_packages — /travel/v1/packages)
// ═══════════════════════════════════════════════════════════════════════════
export type PackageCategory = 'budget' | 'luxury' | 'honeymoon' | 'family'

/**
 * Mirrors `PackageOut` in api/app/routers/travel/packages.py.
 *
 * `base_price_inr` keeps its legacy column name (catalog_service and
 * ai_engine read it) but is NOT necessarily rupees — `currency` says what it
 * is. Always render the two together.
 */
export interface TravelPackage {
  id: string
  business_id: string
  branch_id: string | null
  name: string
  destination_id: string | null
  duration_days: number
  nights: number | null
  base_price_inr: number
  currency: string
  category: PackageCategory | null
  inclusions: string[]
  exclusions: string[]
  itinerary_template: Record<string, unknown>[]
  min_pax: number | null
  max_pax: number | null
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export interface PackageCreatePayload {
  name: string
  destination_id?: string | null
  duration_days: number
  nights?: number | null
  base_price_inr: number
  /** ISO-4217, 3 chars. Defaults to INR server-side. */
  currency?: string
  category?: PackageCategory | null
  branch_id?: string | null
  inclusions?: string[]
  exclusions?: string[]
  itinerary_template?: Record<string, unknown>[]
  min_pax?: number
  max_pax?: number
}

/** PATCH body — every field optional, unset fields untouched. */
export type PackageUpdatePayload = Partial<PackageCreatePayload> & {
  is_active?: boolean
}

// ═══════════════════════════════════════════════════════════════════════════
// Payment links  (/travel/v1/payment-links — router mounts with NO prefix)
// ═══════════════════════════════════════════════════════════════════════════
export type PaymentLinkStatus = 'created' | 'sent' | 'viewed' | 'paid' | 'expired'
export type PaymentGateway = 'razorpay' | 'stripe' | 'stub'

/** A payment_links row (migration 0010), returned raw by the router. */
export interface PaymentLink {
  id: string
  business_id: string
  lead_id: string | null
  package_id: string | null
  /** NUMERIC(12,2) in MAJOR units of `currency` (rupees, not paise). */
  amount: number
  currency: string
  gateway: PaymentGateway
  status: PaymentLinkStatus
  expiry_at: string | null
  gateway_link_id: string | null
  gateway_short_url: string | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface PaymentLinkListResponse {
  count: number
  /** 'razorpay' | 'stub' — whether links are real or `stub://`. Surface it. */
  gateway_mode: string
  items: PaymentLink[]
}

export interface PaymentLinkCreatePayload {
  /** Major units. Sent as a string so no float ever touches money. */
  amount: string
  /** ISO-4217, 3 chars. Defaults to INR server-side. */
  currency?: string
  lead_id?: string | null
  package_id?: string | null
  description?: string
  customer_name?: string | null
  customer_email?: string | null
  customer_phone?: string | null
  /** ISO 8601 UTC. Must be in the future. */
  expiry_at?: string | null
  gateway?: PaymentGateway | null
  notes?: Record<string, unknown> | null
}

/** Forward-only: created → sent → viewed → paid; expired from any non-paid. */
export interface PaymentLinkTransitionPayload {
  status: Exclude<PaymentLinkStatus, 'created'>
}

// ═══════════════════════════════════════════════════════════════════════════
// WhatsApp  (/travel/v1/whatsapp)
// ═══════════════════════════════════════════════════════════════════════════
export type WhatsAppMessageType = 'template' | 'freeform'

/** `stubbed` means the row was recorded and NOTHING was transmitted. */
export type WhatsAppOutboxStatus = 'queued' | 'sent' | 'failed' | 'stubbed'

export interface WhatsAppOutboxEntry {
  id: string
  business_id: string
  to_number: string
  message_type: string
  template_name: string | null
  language: string | null
  payload: Record<string, unknown>
  status: WhatsAppOutboxStatus
  /** Which provider handled it — 'stub' transmits nothing. */
  provider: string
  provider_message_id: string | null
  error: string | null
  created_at: string | null
  sent_at: string | null
}

export interface WhatsAppOutboxPage {
  items: WhatsAppOutboxEntry[]
  total: number
}

export interface WhatsAppSendPayload {
  /** E.164, or a bare 10-digit Indian mobile. */
  to: string
  message_type?: WhatsAppMessageType
  /** Required when message_type === 'template'. */
  template_name?: string | null
  language?: string
  components?: Record<string, unknown>[] | null
  /** Required when message_type === 'freeform'. 409 if the 24h window closed. */
  text?: string | null
}

// ═══════════════════════════════════════════════════════════════════════════
// Reports  (/travel/v1/reports/* and /travel/v1/report-schedules)
// ═══════════════════════════════════════════════════════════════════════════
export type ReportType = 'daily' | 'weekly' | 'monthly'
export type ReportDeliveryChannel = 'whatsapp' | 'email'

export interface ReportPeriod {
  anchor: string
  start: string
  end: string
  days: number
  timezone: string
}

export interface ReportCallsBlock {
  total: number
  completed: number
  failed: number
  active: number
  by_status: Record<string, number>
  by_mode: Record<string, number>
  by_language: Record<string, number>
  total_duration_sec: number
  avg_duration_sec: number
  calls_with_duration: number
  connected_rate_pct: number
}

export interface ReportFunnelBlock {
  leads_total: number
  by_qualification: Record<string, number>
  by_status: Record<string, number>
  qualified_or_better: number
  hot_leads: number
  booked: number
  converted: number
  lost: number
  conversion_rate_pct: number
  leads_from_calls: number
  by_source: Record<string, number>
}

/**
 * Revenue degrades to `available: false` rather than reporting a false 0 —
 * check `available` BEFORE reading any figure.
 *
 * `collected_by_currency` is the only complete answer: it is keyed by
 * ISO-4217 code and is NOT summed across currencies. `collected_inr` is the
 * INR bucket alone, never a converted grand total.
 */
export interface ReportRevenueBlock {
  available: boolean
  source: string
  links_created?: number
  links_paid?: number
  payment_conversion_pct?: number
  collected_by_currency: Record<string, number>
  collected_inr: number | null
  by_link_status?: Record<string, number>
  reason?: string
  note?: string
}

export interface ReportTopPackage {
  package_id: string
  name: string | null
  destination: string | null
  /** Package list price. Currency is on the package row, not repeated here. */
  base_price_inr: number | null
  leads_matched: number
  paid_links: number
  /** null when revenue is unavailable. Same currency mix caveat as above. */
  revenue_attributed: number | null
}

/** Every field is suppressed to null while `stub_derived` is true. */
export interface ReportSentimentBlock {
  samples: number
  distinct_values: number
  is_constant: boolean
  stub_derived: boolean
  detected_via: string[]
  avg_score_raw: number | null
  min_score_raw: number | null
  max_score_raw: number | null
  trend: {
    direction: 'up' | 'down' | 'flat'
    delta: number
    first_half_avg: number
    second_half_avg: number
  } | null
  trend_suppressed_reason: string | null
  label: string | null
}

export interface ReportLeadScoreBlock {
  samples: number
  distinct_values: number
  is_constant: boolean
  stub_derived: boolean
  avg_score_raw: number | null
  label: string
}

export interface ReportDataQuality {
  ai_stub_mode: boolean
  ai_stub_reason: string | null
  trustworthy: string[]
  not_trustworthy: string[]
  rows_scanned: Record<string, number>
  rows_in_period: Record<string, number>
}

/** GET /reports/daily | /weekly | /monthly. Render `warnings` — they say when
 *  a figure is a stub constant rather than a measurement. */
export interface Report {
  report_type: ReportType
  period: ReportPeriod
  scope: { branch_id: string | null; branch_scoped: boolean }
  calls: ReportCallsBlock
  funnel: ReportFunnelBlock
  revenue: ReportRevenueBlock
  top_packages: ReportTopPackage[]
  sentiment: ReportSentimentBlock
  lead_score: ReportLeadScoreBlock
  data_quality: ReportDataQuality
  warnings: string[]
}

/** Mirrors `ReportScheduleOut` in routers/travel/reports.py. */
export interface ReportSchedule {
  id: string
  business_id: string
  report_type: ReportType
  branch_id: string | null
  delivery_channel: ReportDeliveryChannel
  recipients: string[]
  /** Local wall-clock 'HH:MM:SS' in `timezone`, not a UTC instant. */
  send_time: string
  timezone: string
  is_active: boolean
  last_run_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ReportScheduleCreatePayload {
  report_type: ReportType
  delivery_channel: ReportDeliveryChannel
  /** 'HH:MM' or 'HH:MM:SS', local to `timezone`. */
  send_time: string
  recipients?: string[]
  branch_id?: string | null
  timezone?: string
  is_active?: boolean
}

export type ReportSchedulePatchPayload = Partial<ReportScheduleCreatePayload>

/** One verdict from GET /reports/scheduled/due. Non-firing schedules are
 *  returned too (with `due: false` + `reason`) when include_skipped=true. */
export interface ReportScheduleDueVerdict {
  schedule_id: string
  business_id: string
  branch_id: string | null
  report_type: string
  delivery_channel: string
  timezone: string
  local_now: string
  due: boolean
  reason: string | null
  period_key: string | null
  anchor: string | null
  send_time?: string
  next_fire_at_local?: string
}

export type ReportDeliveryStatus =
  | 'sent'
  | 'queued'
  | 'failed'
  | 'partial'
  | 'skipped'
  | 'dry_run'
  | 'unavailable'

export interface ReportDeliveryResult {
  channel: string
  recipients: string[]
  body_chars: number
  dry_run: boolean
  status: ReportDeliveryStatus
  detail?: string
  results?: { to: string; ok: boolean; result?: string; error?: string }[]
}

export interface ReportRunDueResponse {
  now_utc: string
  grace_minutes: number
  dry_run: boolean
  count: number
  dispatched: {
    schedule_id: string
    report_type: string
    delivery_channel: string
    period_key: string | null
    anchor: string | null
    dry_run: boolean
    status: string
    error?: string
    recipients?: string[]
    message_preview?: string
    warnings?: string[]
    delivery?: ReportDeliveryResult
    last_run_at?: string
  }[]
}

export interface ReportSendWhatsAppPayload {
  /** Defaults to TRUE server-side. false actually messages real people. */
  dry_run?: boolean
  /** YYYY-MM-DD. Defaults to "now" in the schedule's timezone. */
  anchor_date?: string | null
  recipients_override?: string[] | null
}

export interface ReportSendWhatsAppResponse {
  schedule_id: string
  report_type: ReportType
  period: ReportPeriod
  message: string
  delivery: ReportDeliveryResult
  warnings: string[]
}

// ═══════════════════════════════════════════════════════════════════════════
// Follow-ups  (/travel/v1/follow-ups)
// ═══════════════════════════════════════════════════════════════════════════
export type FollowUpStatus = 'due' | 'overdue' | 'in_progress' | 'done'
export type FollowUpType = 'nudge' | 'summary' | 'personal_call' | 'price_alert'
export type FollowUpChannel = 'whatsapp' | 'sms' | 'email' | 'call' | 'in_app'
export type LadderDay = 1 | 3 | 7

/**
 * `status` is DERIVED at read time — `due` becomes `overdue` the moment
 * `due_at` passes, with no cron involved. `stored_status` is the raw column.
 * Filter and display on `status`; only reach for `stored_status` when you
 * genuinely need the persisted value.
 */
export interface FollowUp {
  id: string
  business_id: string
  lead_id: string
  branch_id: string | null
  rule_id: string | null
  ladder_day: LadderDay
  type: FollowUpType
  due_at: string
  status: FollowUpStatus
  stored_status: FollowUpStatus
  assigned_to: string | null
  channel: FollowUpChannel
  completed_at: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface FollowUpPatchPayload {
  status?: FollowUpStatus
  assigned_to?: string
  channel?: FollowUpChannel
  /** ISO 8601 UTC. */
  due_at?: string
  metadata?: Record<string, unknown>
}

export interface FollowUpRule {
  id: string
  business_id: string
  branch_id: string | null
  ladder_day: LadderDay
  type: FollowUpType
  channel: FollowUpChannel
  /** null ⇒ derived as ladder_day × 24 hours. */
  due_offset_hours: number | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** GET /follow-ups/rules. `ladder` is resolved (branch overrides business);
 *  `raw_rules` is every stored rule including inactive ones. */
export interface FollowUpRulesResponse {
  branch_id: string | null
  ladder: FollowUpRule[]
  raw_rules: FollowUpRule[]
}

export interface FollowUpRulePayload {
  ladder_day: LadderDay
  type: FollowUpType
  channel?: FollowUpChannel
  due_offset_hours?: number | null
  is_active?: boolean
  branch_id?: string | null
}

/** PUT /follow-ups/rules. `rescheduled` counts FUTURE rows moved by the edit;
 *  due/overdue/in-progress/done rows are provably untouched. */
export interface FollowUpRuleUpsertResponse {
  rule: FollowUpRule
  rescheduled: number
}

export interface FollowUpSchedulePayload {
  lead_id: string
  branch_id?: string | null
  assigned_to?: string | null
}

/** POST /follow-ups/schedule. Idempotent — `created` is [] when the ladder
 *  was already scheduled for that lead. */
export interface FollowUpScheduleResponse {
  lead_id: string
  created: FollowUp[]
  count: number
}

// ═══════════════════════════════════════════════════════════════════════════
// Activity log  (/travel/v1/activity-log — read-only by design)
// ═══════════════════════════════════════════════════════════════════════════
export type ActivityEntityType =
  | 'call'
  | 'lead'
  | 'follow_up'
  | 'package'
  | 'booking'
  | 'payment_link'
  | 'ai_config'
  | 'user'
  | 'branch'
  | 'whatsapp_message'
  | 'report'
  | 'business'
  | 'other'

export interface ActivityLogEntry {
  id: string
  business_id: string
  /** null = system/automated actor (webhook, scheduler, AI engine). */
  actor_id: string | null
  /** Dotted verb, e.g. 'call.takeover.full'. Vocabulary grows every phase. */
  action: string
  entity_type: ActivityEntityType
  entity_id: string | null
  branch_id: string | null
  metadata: Record<string, unknown>
  /** ISO 8601 UTC. The column is `at`, not `created_at`. */
  at: string
}

// ═══════════════════════════════════════════════════════════════════════════
// Cost & usage analytics  (/travel/v1/analytics)
// ═══════════════════════════════════════════════════════════════════════════
// EVERY figure here is an ESTIMATE unless a line item's `is_estimated` is
// false. No provider usage API is integrated, so nothing has been metered.
// Any UI showing these MUST surface the estimated label next to the number.

export type CostBasis = 'ESTIMATED' | 'METERED'

export interface UsageLineItem {
  id: string
  call_id: string | null
  branch_id: string | null
  at: string
  stt_engine: string | null
  stt_seconds: number | null
  llm_input_tokens: number | null
  llm_output_tokens: number | null
  tts_characters: number | null
  telephony_seconds: number | null
  /** USD. Decimal-as-number from NUMERIC; the currency is always USD here. */
  cost_usd: number | null
  cost_breakdown: Record<string, number>
  is_estimated: boolean
  cost_basis: CostBasis
  rate_card_version: string | null
}

/** Decimal strings, always USD. */
export interface UsageCostBucket {
  rows: number
  cost_usd: string
  components: { stt: string; llm: string; tts: string; telephony: string }
}

/** `estimated` and `metered` are deliberately NEVER summed — there is no
 *  combined total key, and adding them yourself produces a meaningless
 *  number. Render them as two figures. */
export interface UsageSummary {
  estimated: UsageCostBucket
  metered: UsageCostBucket
  units: {
    stt_seconds: string
    telephony_seconds: string
    llm_input_tokens: number
    llm_output_tokens: number
    tts_characters: number
    minutes: string
  }
  estimated_cost_per_minute: string | null
  note: string
}

export interface UsageRateCardRates {
  stt_per_second: Record<string, string>
  llm_per_1k_input: Record<string, string>
  llm_per_1k_output: Record<string, string>
  tts_per_1k_characters: Record<string, string>
  telephony_per_second: Record<string, string>
}

export interface CostReport {
  period: { token: string; start: string; end: string }
  branch_id: string | null
  summary: UsageSummary
  line_items: UsageLineItem[]
  /** USD per modelled conversational minute. */
  targets_usd_per_min: Record<string, { low: string; high: string }>
  cost_basis: CostBasis | 'MIXED'
  all_estimated: boolean
  rate_card: {
    version: string
    formula: string
    rates_usd: UsageRateCardRates
    provenance: string
  }
  disclaimer: string
}

export interface RateCard {
  rate_card_version: string
  formula: string
  rates_usd: UsageRateCardRates
  targets_usd_per_min: Record<string, { low: string; high: string }>
  per_minute_model: Record<string, Record<string, string | boolean | null>>
  provenance: string
  all_estimated: boolean
  disclaimer: string
}

// ── Multi-currency revenue rollup ──────────────────────────────────────────
/** One converted payment. `amount`+`currency` are the native pair; `amount_inr`
 *  is the point-in-time conversion at `rate_as_of` (the row's OWN timestamp). */
export interface RevenueRollupLineItem {
  id: string | null
  currency: string
  amount: string | null
  at: string | null
  rate: string
  rate_as_of: string
  amount_inr: string
}

/** A payment that could NOT be converted. It was not dropped and not counted
 *  as zero — it is excluded from `total`. Show it. */
export interface RevenueRollupUnconvertibleItem {
  id: string | null
  currency: string
  amount: string | null
  at: string | null
  rate: null
  reason: string
}

export interface RevenueRollupCurrencyBucket {
  currency: string
  rows: number
  native_amount: string
  converted_inr: string
}

/**
 * GET /analytics/revenue-rollup.
 *
 * READ `complete` BEFORE `total`. When `complete` is false the total omits
 * every row in `unconvertible` — presenting it as the period's revenue is
 * wrong. `total` is a decimal string in `quote_currency` (INR).
 */
export interface RevenueRollup {
  period: { token: string; start: string; end: string }
  branch_id: string | null
  status_filter: string
  quote_currency: string
  complete: boolean
  total_is_partial: boolean
  total: string
  total_note: string
  rows_in: number
  rows_converted: number
  rows_unconvertible: number
  by_currency: RevenueRollupCurrencyBucket[]
  unconvertible: {
    rows: number
    currencies: string[]
    by_currency: {
      currency: string
      rows: number
      native_amount: string
      reasons: string[]
    }[]
    items: RevenueRollupUnconvertibleItem[]
    remedy: string
  }
  line_items: RevenueRollupLineItem[]
  conversion_basis: string
  timestamp_field: string
  branch_attribution: {
    requested_branch_id: string | null
    derivation: string
    schema_note: string
    excluded_unattributable_rows: number
    excluded_unattributable_ids: string[]
  }
  fx: {
    resolver: string
    snapshots_considered: number
    forward_fill: boolean
    live_rate_used: boolean
    determinism: string
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// AI config  (/travel/v1/ai-config)
// ═══════════════════════════════════════════════════════════════════════════
export interface AiConfigQuestion {
  order: number
  question: string
  field: string
}

export interface AiConfigWorkingHours {
  start: string
  end: string
  timezone: string
}

export interface AiConfigVoicePersona {
  name: string
  tone: string
  greeting: string
}

/** travel_ai_config row. Branch-scoped when the caller's token carries a
 *  branch_id, otherwise the business-wide row. */
export interface AiConfig {
  id: string
  business_id: string
  branch_id: string | null
  question_flow: AiConfigQuestion[]
  /** First element is the default language. */
  languages: string[]
  escalation_rules: Record<string, unknown>
  working_hours: AiConfigWorkingHours
  voice_persona: AiConfigVoicePersona
  created_at: string
  updated_at: string
}

/** PUT body. Nulls are stripped server-side; an empty body is a 422. */
export interface AiConfigPatchPayload {
  question_flow?: AiConfigQuestion[]
  languages?: string[]
  escalation_rules?: Record<string, unknown>
  working_hours?: AiConfigWorkingHours
  voice_persona?: AiConfigVoicePersona
}

// ═══════════════════════════════════════════════════════════════════════════
// Users & branches  (/techscape/v1 — platform surface, not /travel/v1)
// ═══════════════════════════════════════════════════════════════════════════
/** Stored role values. The product's "admin tier" is stored as `manager`
 *  (see api/app/core/deps.py). UI gating on these is UX, never security. */
export type TeamRole = 'super_admin' | 'admin' | 'manager' | 'agent' | 'viewer' | 'user'
export type UserStatus = 'active' | 'inactive' | 'suspended'

export interface TeamUser {
  id: string
  business_id: string
  branch_id: string | null
  email: string
  first_name: string | null
  last_name: string | null
  role: string
  status: string
  last_login_at: string | null
  created_at: string
  updated_at: string
}

export interface TeamUserListResponse {
  items: TeamUser[]
  total: number
}

export interface TeamUserCreatePayload {
  email: string
  /** Min 8 chars. */
  password: string
  first_name?: string | null
  last_name?: string | null
  role?: string
  branch_id?: string | null
}

export interface TeamUserUpdatePayload {
  first_name?: string | null
  last_name?: string | null
  branch_id?: string | null
  role?: string
  status?: UserStatus
}

/** DELETE /users/{id} is a soft deactivate — it returns the new status. */
export interface TeamUserDeleteResponse {
  id: string
  status: string
}

export type BranchStatus = 'active' | 'inactive'

export interface Branch {
  id: string
  business_id: string
  name: string
  city: string | null
  status: string
  created_at: string
}

/** GET /branches/{id} returns the branch plus an aggregate stats blob. */
export interface BranchWithStats extends Branch {
  stats: Record<string, unknown>
}

export interface BranchListResponse {
  items: Branch[]
  total: number
}

export interface BranchCreatePayload {
  name: string
  city?: string | null
  status?: BranchStatus
}
