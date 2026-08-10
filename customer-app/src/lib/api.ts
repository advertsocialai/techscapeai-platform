import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import type { LoginPayload, LoginResponse, RegisterPayload } from '../types/auth'

const ACCESS_KEY = 'gogaga_access_token'
const REFRESH_KEY = 'gogaga_refresh_token'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/techscape/v1',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(ACCESS_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

/* ────────────────────────────────────────────────────────────────────────
 * Token refresh
 *
 * The previous interceptor logged the user out on ANY 401 without ever
 * attempting a refresh. Access tokens live 15 minutes (JWT_ACCESS_TTL_MIN)
 * while refresh tokens live 7 days, and POST /auth/refresh exists — so a
 * customer was being bounced to the login screen every quarter of an hour
 * while holding a perfectly valid refresh token.
 *
 * SHARED IN-FLIGHT PROMISE, and it is load-bearing rather than tidy:
 * /auth/refresh issues a NEW refresh token every time (rotation). If two
 * requests 401 together and each refreshed independently, the second would
 * present a token the first had already spent, and the session would hard-fail.
 * One promise, shared by every waiter.
 *
 * Retry is attempted exactly once per request (`_retried`). Without that flag a
 * genuinely-unauthorised call would refresh, retry, 401, refresh… forever.
 * ──────────────────────────────────────────────────────────────────────── */

type RetriableConfig = AxiosRequestConfig & { _retried?: boolean }

let refreshPromise: Promise<string> | null = null

function clearSession() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

async function refreshAccessToken(): Promise<string> {
  const refreshToken = localStorage.getItem(REFRESH_KEY)
  if (!refreshToken) throw new Error('No refresh token')

  // A bare axios call, NOT `api` — going through the instance would re-enter
  // this interceptor and recurse if the refresh itself 401s.
  const res = await axios.post<LoginResponse>(
    `${api.defaults.baseURL}/auth/refresh`,
    { refresh_token: refreshToken },
    { headers: { 'Content-Type': 'application/json' } },
  )

  localStorage.setItem(ACCESS_KEY, res.data.access_token)
  // The rotated refresh token MUST be stored, or the next refresh presents a
  // spent one and the session dies at the 15-minute mark anyway.
  if (res.data.refresh_token) localStorage.setItem(REFRESH_KEY, res.data.refresh_token)
  return res.data.access_token
}

api.interceptors.response.use(
  (res) => res,
  async (err: AxiosError) => {
    const original = err.config as RetriableConfig | undefined
    const status = err.response?.status

    if (status !== 401 || !original || original._retried) {
      if (status === 401) {
        clearSession()
        window.location.href = '/onboarding/login'
      }
      return Promise.reject(err)
    }

    original._retried = true

    try {
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null
        })
      }
      const token = await refreshPromise
      original.headers = { ...original.headers, Authorization: `Bearer ${token}` }
      return api(original)
    } catch {
      // The refresh token is expired or revoked — this one really is a logout.
      clearSession()
      window.location.href = '/onboarding/login'
      return Promise.reject(err)
    }
  },
)

export const authApi = {
  login: (payload: LoginPayload) => api.post<LoginResponse>('/auth/login', payload),

  register: (payload: RegisterPayload) => api.post('/auth/register-business', payload),

  sendOtp: (email: string) => api.post('/auth/otp/send', { email }),

  verifyOtp: (email: string, code: string) => api.post('/auth/otp/verify', { email, code }),

  me: () => api.get('/auth/me'),

  forgotPassword: (email: string) => api.post('/auth/password/forgot', { email }),

  refresh: (refreshToken: string) =>
    api.post<LoginResponse>('/auth/refresh', { refresh_token: refreshToken }),
}

export default api
