import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { authApi } from './api'
import type { MeResponse, RegisterPayload } from '../types/auth'

interface AuthContextValue {
  me: MeResponse | null
  loading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  register: (payload: RegisterPayload) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const token = localStorage.getItem('gogaga_access_token')
    if (!token) {
      setLoading(false)
      return
    }
    authApi
      .me()
      .then(setMe)
      .catch(() => {
        localStorage.removeItem('gogaga_access_token')
        localStorage.removeItem('gogaga_refresh_token')
      })
      .finally(() => setLoading(false))
  }, [])

  async function login(email: string, password: string) {
    setError(null)
    try {
      const tokens = await authApi.login({ email, password })
      localStorage.setItem('gogaga_access_token', tokens.access_token)
      localStorage.setItem('gogaga_refresh_token', tokens.refresh_token)
      const meRes = await authApi.me()
      setMe(meRes)
    } catch (err) {
      const message =
        (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ||
        'Login failed'
      setError(message)
      throw err
    }
  }

  async function register(payload: RegisterPayload) {
    setError(null)
    let registered = false
    try {
      await authApi.register(payload)
      registered = true
      await login(payload.contact_email, payload.user_password)
    } catch (err) {
      if (registered) {
        // The account was created, but the auto-login that follows failed
        // (e.g. a transient backend hiccup) — don't tell the user signup
        // itself failed, since retrying would just 409 on "already exists".
        throw new Error('ACCOUNT_CREATED_LOGIN_FAILED')
      }
      const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Registration failed')
      throw err
    }
  }

  function logout() {
    localStorage.removeItem('gogaga_access_token')
    localStorage.removeItem('gogaga_refresh_token')
    setMe(null)
  }

  return (
    <AuthContext.Provider value={{ me, loading, error, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
