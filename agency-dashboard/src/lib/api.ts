import axios from 'axios'
import type {
  LoginPayload,
  RegisterPayload,
  TokenResponse,
  MeResponse,
  ForgotPasswordPayload,
  ResetPasswordPayload,
} from '../types/auth'
import type { Lead, LeadStatus, Booking, PlaybookSummary, PlaybookRun } from '../types/travel'

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

export default api
