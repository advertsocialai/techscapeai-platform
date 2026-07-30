import axios from 'axios'
import type { LoginPayload, LoginResponse, RegisterPayload } from '../types/auth'

const api = axios.create({
  baseURL: `${import.meta.env.VITE_API_URL}/api/techscape/v1`,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/onboarding/login'
    }
    return Promise.reject(err)
  }
)

export const authApi = {
  login: (payload: LoginPayload) =>
    api.post<LoginResponse>('/auth/login', payload),

  register: (payload: RegisterPayload) =>
    api.post('/auth/register-business', payload),

  sendOtp: (email: string) =>
    api.post('/auth/otp/send', { email }),

  verifyOtp: (email: string, code: string) =>
    api.post('/auth/otp/verify', { email, code }),

  me: () => api.get('/auth/me'),

  forgotPassword: (email: string) =>
    api.post('/auth/password/forgot', { email }),
}

export default api