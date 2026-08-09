import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { authApi } from './api'
import { errorMessage } from './errors'
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
  const [loading, setLoading] = useState(() => !!localStorage.getItem('gogaga_access_token'))
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const token = localStorage.getItem('gogaga_access_token')
    if (!token) return
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
      setError(errorMessage(err))
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
        throw new Error('ACCOUNT_CREATED_LOGIN_FAILED', { cause: err })
      }
      // The `typeof detail === 'string'` guard avoided the crash but threw the
      // useful half away: a 422 array carries the exact rule that failed, and
      // the user got the word "Registration failed" instead.
      setError(errorMessage(err))
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

// eslint-disable-next-line react-refresh/only-export-components -- hook is colocated with its provider by design
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
