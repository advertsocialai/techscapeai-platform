import axios from 'axios'
import type {
  LoginPayload,
  RegisterPayload,
  TokenResponse,
  MeResponse,
  ForgotPasswordPayload,
  ResetPasswordPayload,
} from '../types/auth'
import type {
  Lead,
  LeadStatus,
  Booking,
  PlaybookSummary,
  PlaybookRun,
  Call,
  TranscriptLine,
  CallEvent,
  TakeoverPayload,
  TravelPackage,
  PackageCategory,
  PackageCreatePayload,
  PackageUpdatePayload,
  PaymentLink,
  PaymentLinkListResponse,
  PaymentLinkStatus,
  PaymentLinkCreatePayload,
  PaymentLinkTransitionPayload,
  WhatsAppOutboxEntry,
  WhatsAppOutboxPage,
  WhatsAppOutboxStatus,
  WhatsAppMessageType,
  WhatsAppSendPayload,
  Report,
  ReportType,
  ReportSchedule,
  ReportScheduleCreatePayload,
  ReportSchedulePatchPayload,
  ReportScheduleDueVerdict,
  ReportRunDueResponse,
  ReportSendWhatsAppPayload,
  ReportSendWhatsAppResponse,
  FollowUp,
  FollowUpStatus,
  FollowUpPatchPayload,
  FollowUpRulesResponse,
  FollowUpRulePayload,
  FollowUpRuleUpsertResponse,
  FollowUpSchedulePayload,
  FollowUpScheduleResponse,
  ActivityLogEntry,
  ActivityEntityType,
  CostReport,
  RateCard,
  RevenueRollup,
  AiConfig,
  AiConfigPatchPayload,
  TeamUser,
  TeamUserListResponse,
  TeamUserCreatePayload,
  TeamUserUpdatePayload,
  TeamUserDeleteResponse,
  Branch,
  BranchWithStats,
  BranchListResponse,
  BranchCreatePayload,
} from '../types/travel'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('gogaga_access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

function clearSessionAndRedirect() {
  localStorage.removeItem('gogaga_access_token')
  localStorage.removeItem('gogaga_refresh_token')
  if (!window.location.pathname.endsWith('/login') && !window.location.pathname.endsWith('/signup')) {
    window.location.href = '/login'
  }
}

// Concurrent requests can all 401 at once (e.g. Mission Control fires 3
// queries in parallel) — share a single in-flight refresh so we don't fire
// multiple /auth/refresh calls, which would race since the refresh token
// rotates on every use and a second call with the already-spent token 401s.
let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refreshToken = localStorage.getItem('gogaga_refresh_token')
      if (!refreshToken) throw new Error('No refresh token')
      const { data } = await axios.post<TokenResponse>('/api/techscape/v1/auth/refresh', {
        refresh_token: refreshToken,
      })
      localStorage.setItem('gogaga_access_token', data.access_token)
      localStorage.setItem('gogaga_refresh_token', data.refresh_token)
      return data.access_token
    })().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    const isAuthBootstrapCall = ['/auth/login', '/auth/register-business', '/auth/refresh'].some(
      (path) => original?.url?.includes(path),
    )
    if (err.response?.status === 401 && !original?._retried && !isAuthBootstrapCall) {
      original._retried = true
      try {
        const newToken = await refreshAccessToken()
        original.headers.Authorization = `Bearer ${newToken}`
        return api.request(original)
      } catch {
        clearSessionAndRedirect()
        return Promise.reject(err)
      }
    }
    if (err.response?.status === 401) {
      clearSessionAndRedirect()
    }
    return Promise.reject(err)
  },
)

export const authApi = {
  login: (payload: LoginPayload) =>
    api.post<TokenResponse>('/techscape/v1/auth/login', payload).then((r) => r.data),
  register: (payload: RegisterPayload) =>
    api.post('/techscape/v1/auth/register-business', payload).then((r) => r.data),
  me: () => api.get<MeResponse>('/techscape/v1/auth/me').then((r) => r.data),
  forgotPassword: (payload: ForgotPasswordPayload) =>
    api.post<{ ok: boolean; reset_token?: string }>('/techscape/v1/auth/password/forgot', payload).then((r) => r.data),
  resetPassword: (payload: ResetPasswordPayload) =>
    api.post<{ ok: boolean }>('/techscape/v1/auth/password/reset', payload).then((r) => r.data),
}

export const leadsApi = {
  list: (params?: { status?: LeadStatus; qualification?: string }) =>
    api.get<Lead[]>('/travel/v1/leads', { params }).then((r) => r.data),
  get: (id: string) => api.get<Lead>(`/travel/v1/leads/${id}`).then((r) => r.data),
  updateStatus: (id: string, status: LeadStatus) =>
    api.put<Lead>(`/travel/v1/leads/${id}/status`, { status }).then((r) => r.data),
  // PUT /leads/{id}/assign — pass null to unassign.
  assign: (id: string, assignedAgent: string | null) =>
    api
      .put<Lead>(`/travel/v1/leads/${id}/assign`, { assigned_agent: assignedAgent })
      .then((r) => r.data),
}

export const bookingsApi = {
  list: () => api.get<Booking[]>('/travel/v1/bookings').then((r) => r.data),
  get: (id: string) => api.get<Booking>(`/travel/v1/bookings/${id}`).then((r) => r.data),
}

export const playbooksApi = {
  list: () => api.get<PlaybookSummary[]>('/travel/v1/playbooks').then((r) => r.data),
  get: (ucId: string) => api.get(`/travel/v1/playbooks/${ucId}`).then((r) => r.data),
  render: (ucId: string, context: Record<string, unknown> = {}) =>
    api.post(`/travel/v1/playbooks/${ucId}/render`, { context }).then((r) => r.data),
  runs: (params?: { use_case_id?: string; limit?: number }) =>
    api.get<PlaybookRun[]>('/travel/v1/playbooks/runs', { params }).then((r) => r.data),
}

export const customersApi = {
  get: (id: string) => api.get(`/travel/v1/customers/${id}`).then((r) => r.data),
}

// ═══════════════════════════════════════════════════════════════════════════
// Calls — /travel/v1/calls (routers/travel/calls.py + takeover.py, both
// mounted under prefix="/calls").
// The live transcript stream is the WS at /ws/calls/{id} (src/lib/ws.ts);
// `transcript` below is the historical fetch, not a substitute for it.
// ═══════════════════════════════════════════════════════════════════════════
export const callsApi = {
  live: () => api.get<Call[]>('/travel/v1/calls/live').then((r) => r.data),
  transcript: (callId: string) =>
    api.get<TranscriptLine[]>(`/travel/v1/calls/${callId}/transcript`).then((r) => r.data),
  events: (callId: string) =>
    api.get<CallEvent[]>(`/travel/v1/calls/${callId}/events`).then((r) => r.data),
}

// ═══════════════════════════════════════════════════════════════════════════
// Takeover — POST /travel/v1/calls/{id}/takeover/*
//
// These change a LIVE phone call. The returned `Call` (CallOut) does NOT
// carry takeover_state — never render a takeover as succeeded off the back of
// this promise. The visual source of truth is the `takeover_state` WS
// broadcast. 409 means the state machine refused the transition (or the call
// is not active); surface it, do not retry blindly.
// ═══════════════════════════════════════════════════════════════════════════
export const takeoverApi = {
  monitor: (callId: string, payload: TakeoverPayload = {}) =>
    api.post<Call>(`/travel/v1/calls/${callId}/takeover/monitor`, payload).then((r) => r.data),
  barge: (callId: string, payload: TakeoverPayload = {}) =>
    api.post<Call>(`/travel/v1/calls/${callId}/takeover/barge`, payload).then((r) => r.data),
  // full/release take no body — the server declares no request model for them.
  full: (callId: string) =>
    api.post<Call>(`/travel/v1/calls/${callId}/takeover/full`).then((r) => r.data),
  release: (callId: string) =>
    api.post<Call>(`/travel/v1/calls/${callId}/takeover/release`).then((r) => r.data),
}

// ═══════════════════════════════════════════════════════════════════════════
// Packages — /travel/v1/packages (mounted with prefix="/packages")
// ═══════════════════════════════════════════════════════════════════════════
export const packagesApi = {
  list: (params?: {
    category?: PackageCategory
    destination_id?: string
    include_inactive?: boolean
    limit?: number
    offset?: number
  }) => api.get<TravelPackage[]>('/travel/v1/packages', { params }).then((r) => r.data),
  get: (id: string) =>
    api.get<TravelPackage>(`/travel/v1/packages/${id}`).then((r) => r.data),
  create: (payload: PackageCreatePayload) =>
    api.post<TravelPackage>('/travel/v1/packages', payload).then((r) => r.data),
  update: (id: string, payload: PackageUpdatePayload) =>
    api.patch<TravelPackage>(`/travel/v1/packages/${id}`, payload).then((r) => r.data),
  // SOFT delete — flips is_active to false and returns the archived row.
  remove: (id: string) =>
    api.delete<TravelPackage>(`/travel/v1/packages/${id}`).then((r) => r.data),
}

// ═══════════════════════════════════════════════════════════════════════════
// Payment links — /travel/v1/payment-links
//
// routers/travel/payments.py mounts with NO prefix and declares its own full
// paths, so there is no `/payments` segment anywhere. These move real money:
// check `gateway_mode` on the list response ('stub' means the links are
// `stub://` and nothing can be charged).
// ═══════════════════════════════════════════════════════════════════════════
export const paymentsApi = {
  list: (params?: { lead_id?: string; status?: PaymentLinkStatus; limit?: number }) =>
    api.get<PaymentLinkListResponse>('/travel/v1/payment-links', { params }).then((r) => r.data),
  get: (id: string) =>
    api.get<PaymentLink>(`/travel/v1/payment-links/${id}`).then((r) => r.data),
  create: (payload: PaymentLinkCreatePayload) =>
    api.post<PaymentLink>('/travel/v1/payment-links', payload).then((r) => r.data),
  // Forward-only status machine. Same-status is an idempotent no-op; an
  // illegal transition is a 409 and never demotes a paid link.
  transition: (id: string, payload: PaymentLinkTransitionPayload) =>
    api
      .post<PaymentLink>(`/travel/v1/payment-links/${id}/transition`, payload)
      .then((r) => r.data),
}

// ═══════════════════════════════════════════════════════════════════════════
// WhatsApp — /travel/v1/whatsapp (mounted with prefix="/whatsapp")
//
// `send` messages a real person when credentials exist. Read the returned
// row's `status`/`provider`: 'stubbed' means it was recorded and NOTHING was
// transmitted. 409 = the 24-hour session window is closed, so a free-form
// message is not permitted and an approved template is required.
// ═══════════════════════════════════════════════════════════════════════════
export const whatsappApi = {
  send: (payload: WhatsAppSendPayload) =>
    api.post<WhatsAppOutboxEntry>('/travel/v1/whatsapp/send', payload).then((r) => r.data),
  outbox: (params?: {
    status?: WhatsAppOutboxStatus
    message_type?: WhatsAppMessageType
    to_number?: string
    limit?: number
    offset?: number
  }) => api.get<WhatsAppOutboxPage>('/travel/v1/whatsapp/outbox', { params }).then((r) => r.data),
  outboxEntry: (id: string) =>
    api.get<WhatsAppOutboxEntry>(`/travel/v1/whatsapp/outbox/${id}`).then((r) => r.data),
}

// ═══════════════════════════════════════════════════════════════════════════
// Reports — /travel/v1/reports/* and /travel/v1/report-schedules
//
// routers/travel/reports.py mounts with NO prefix and declares both path
// roots itself, so report-schedules is a sibling of reports, not a child.
// ═══════════════════════════════════════════════════════════════════════════
type ReportParams = {
  /** YYYY-MM-DD. Any date inside the period for weekly/monthly. */
  date?: string
  branch_id?: string
  /** IANA timezone; defaults to Asia/Kolkata server-side. */
  tz?: string
}

export const reportsApi = {
  daily: (params?: ReportParams) =>
    api.get<Report>('/travel/v1/reports/daily', { params }).then((r) => r.data),
  weekly: (params?: ReportParams) =>
    api.get<Report>('/travel/v1/reports/weekly', { params }).then((r) => r.data),
  monthly: (params?: ReportParams) =>
    api.get<Report>('/travel/v1/reports/monthly', { params }).then((r) => r.data),

  scheduledDue: (params?: { include_skipped?: boolean; grace_minutes?: number }) =>
    api
      .get<ReportScheduleDueVerdict[]>('/travel/v1/reports/scheduled/due', { params })
      .then((r) => r.data),
  // dry_run defaults to TRUE server-side. Pass false only to really deliver.
  runDue: (params?: { dry_run?: boolean; grace_minutes?: number }) =>
    api
      .post<ReportRunDueResponse>('/travel/v1/reports/scheduled/run-due', null, { params })
      .then((r) => r.data),

  // Returns print-ready HTML, not PDF bytes (?format=pdf answers 501).
  html: (scheduleId: string, params?: { date?: string }) =>
    api
      .get<string>(`/travel/v1/reports/${scheduleId}/pdf`, {
        params: { ...params, format: 'html' },
        responseType: 'text',
      })
      .then((r) => r.data),
  sendWhatsApp: (scheduleId: string, payload: ReportSendWhatsAppPayload = {}) =>
    api
      .post<ReportSendWhatsAppResponse>(
        `/travel/v1/reports/${scheduleId}/send-whatsapp`,
        payload,
      )
      .then((r) => r.data),

  listSchedules: (params?: {
    report_type?: ReportType
    is_active?: boolean
    limit?: number
  }) => api.get<ReportSchedule[]>('/travel/v1/report-schedules', { params }).then((r) => r.data),
  getSchedule: (id: string) =>
    api.get<ReportSchedule>(`/travel/v1/report-schedules/${id}`).then((r) => r.data),
  createSchedule: (payload: ReportScheduleCreatePayload) =>
    api.post<ReportSchedule>('/travel/v1/report-schedules', payload).then((r) => r.data),
  updateSchedule: (id: string, payload: ReportSchedulePatchPayload) =>
    api.patch<ReportSchedule>(`/travel/v1/report-schedules/${id}`, payload).then((r) => r.data),
  // 204 No Content.
  deleteSchedule: (id: string) =>
    api.delete<void>(`/travel/v1/report-schedules/${id}`).then((r) => r.data),
}

// ═══════════════════════════════════════════════════════════════════════════
// Follow-ups — /travel/v1/follow-ups (mounted with prefix="/follow-ups")
//
// `status` on each row is derived at read time, so ?status=overdue works with
// no sweep job. The branch filter's query key is `branch`, not `branch_id`.
// ═══════════════════════════════════════════════════════════════════════════
export const followUpsApi = {
  list: (params?: {
    status?: FollowUpStatus
    lead_id?: string
    branch?: string
    limit?: number
  }) => api.get<FollowUp[]>('/travel/v1/follow-ups', { params }).then((r) => r.data),
  update: (id: string, payload: FollowUpPatchPayload) =>
    api.patch<FollowUp>(`/travel/v1/follow-ups/${id}`, payload).then((r) => r.data),
  rules: () =>
    api.get<FollowUpRulesResponse>('/travel/v1/follow-ups/rules').then((r) => r.data),
  // Cascades to FUTURE-scheduled follow-ups only; `rescheduled` says how many.
  upsertRule: (payload: FollowUpRulePayload) =>
    api.put<FollowUpRuleUpsertResponse>('/travel/v1/follow-ups/rules', payload).then((r) => r.data),
  // Idempotent — `created` is [] when the ladder already exists for the lead.
  schedule: (payload: FollowUpSchedulePayload) =>
    api
      .post<FollowUpScheduleResponse>('/travel/v1/follow-ups/schedule', payload)
      .then((r) => r.data),
}

// ═══════════════════════════════════════════════════════════════════════════
// Activity log — GET /travel/v1/activity-log (prefix="/activity-log")
// Read-only by design: there is no write endpoint, and there must not be.
// ═══════════════════════════════════════════════════════════════════════════
export const activityApi = {
  list: (params?: {
    actor?: string
    /** entity_type, e.g. 'call'. */
    entity?: ActivityEntityType
    entity_id?: string
    branch?: string
    /** Exact dotted verb, e.g. 'call.takeover.full'. */
    action?: string
    limit?: number
  }) => api.get<ActivityLogEntry[]>('/travel/v1/activity-log', { params }).then((r) => r.data),
}

// ═══════════════════════════════════════════════════════════════════════════
// Cost / usage / revenue — /travel/v1/analytics (prefix="/analytics")
//
// Every cost figure is an ESTIMATE unless a line item's is_estimated is false.
// On the rollup, read `complete` before `total` — an incomplete total omits
// the rows listed under `unconvertible`.
// ═══════════════════════════════════════════════════════════════════════════
type AnalyticsParams = {
  /** 'today', 'mtd', or '<N>d' (7d/30d/90d). Defaults to 30d. */
  period?: string
  branch?: string
  limit?: number
}

export const usageApi = {
  cost: (params?: AnalyticsParams) =>
    api.get<CostReport>('/travel/v1/analytics/cost', { params }).then((r) => r.data),
  rateCard: () =>
    api.get<RateCard>('/travel/v1/analytics/cost/rate-card').then((r) => r.data),
  revenueRollup: (params?: AnalyticsParams) =>
    api.get<RevenueRollup>('/travel/v1/analytics/revenue-rollup', { params }).then((r) => r.data),
}

// ═══════════════════════════════════════════════════════════════════════════
// AI config — /travel/v1/ai-config (prefix="/ai-config")
// The GET auto-seeds on first access, so it never 404s.
// ═══════════════════════════════════════════════════════════════════════════
export const aiConfigApi = {
  get: () => api.get<AiConfig>('/travel/v1/ai-config').then((r) => r.data),
  update: (payload: AiConfigPatchPayload) =>
    api.put<AiConfig>('/travel/v1/ai-config', payload).then((r) => r.data),
  seed: () => api.post<AiConfig>('/travel/v1/ai-config/seed').then((r) => r.data),
}

// ═══════════════════════════════════════════════════════════════════════════
// Users & branches — /techscape/v1 (platform surface, NOT /travel/v1)
// ═══════════════════════════════════════════════════════════════════════════
export const usersApi = {
  list: (params?: { role?: string; status?: string; limit?: number; offset?: number }) =>
    api.get<TeamUserListResponse>('/techscape/v1/users', { params }).then((r) => r.data),
  get: (id: string) => api.get<TeamUser>(`/techscape/v1/users/${id}`).then((r) => r.data),
  create: (payload: TeamUserCreatePayload) =>
    api.post<TeamUser>('/techscape/v1/users', payload).then((r) => r.data),
  update: (id: string, payload: TeamUserUpdatePayload) =>
    api.patch<TeamUser>(`/techscape/v1/users/${id}`, payload).then((r) => r.data),
  // Deactivates rather than destroys — returns the resulting status.
  deactivate: (id: string) =>
    api.delete<TeamUserDeleteResponse>(`/techscape/v1/users/${id}`).then((r) => r.data),
}

export const branchesApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get<BranchListResponse>('/techscape/v1/branches', { params }).then((r) => r.data),
  // Returns the branch plus an aggregate `stats` blob.
  get: (id: string) =>
    api.get<BranchWithStats>(`/techscape/v1/branches/${id}`).then((r) => r.data),
  create: (payload: BranchCreatePayload) =>
    api.post<Branch>('/techscape/v1/branches', payload).then((r) => r.data),
}

export default api
