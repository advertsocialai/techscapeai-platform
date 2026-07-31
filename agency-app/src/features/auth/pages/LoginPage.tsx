import { useState } from "react"
import { authApi } from "../../../lib/api"

interface LoginPageProps {
  onLoginSuccess: () => void
}

export default function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function handleLogin() {
    if (!email || !password) {
      setError("Please enter email and password")
      return
    }
    setLoading(true)
    setError("")
    try {
      const res = await authApi.login({ email, password })
      localStorage.setItem("agency_access_token", res.data.access_token)
      onLoginSuccess()
    } catch (err: any) {
      setError(err.response?.data?.detail || "Login failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "linear-gradient(160deg, #060F26 0%, #0C1E52 30%, #112360 55%, #0B1A44 80%, #060F26 100%)",
      fontFamily: "Outfit, sans-serif",
    }}>
      <div style={{ width: 380, textAlign: "center" }}>

        <div style={{ fontSize: 26, fontWeight: 800, color: "#fff", marginBottom: 2, letterSpacing: -0.5 }}>
          Klara
        </div>
        <div style={{ fontSize: 10, fontWeight: 600, color: "rgba(247,169,124,0.7)", letterSpacing: 2, textTransform: "uppercase", marginBottom: 24 }}>
          Agency Dashboard
        </div>

        <div style={{
          background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.11)",
          borderRadius: 24, padding: "28px 26px", backdropFilter: "blur(20px)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06), 0 24px 64px rgba(0,0,0,0.35)",
          textAlign: "left",
        }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#fff", marginBottom: 4 }}>
            Welcome back
          </div>
          <div style={{ fontSize: 12, color: "rgba(255,255,255,0.42)", marginBottom: 20 }}>
            Sign in to your workspace
          </div>

          {error && (
            <div style={{
              background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.25)",
              borderRadius: 10, padding: "9px 12px", marginBottom: 14, fontSize: 12, color: "#F87171",
            }}>
              {error}
            </div>
          )}

          <label style={{ display: "block", fontSize: 9.5, fontWeight: 700, color: "rgba(255,255,255,0.3)", letterSpacing: 0.8, textTransform: "uppercase", marginBottom:6 }}>
            Email
          </label>
          <input
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{
              width: "100%", height: 46, background: "rgba(255,255,255,0.07)",
              border: "1px solid rgba(255,255,255,0.11)", borderRadius: 12, padding: "0 14px",
              color: "#fff", fontSize: 13, marginBottom: 14, outline: "none", boxSizing: "border-box",
            }}
          />

          <label style={{ display: "block", fontSize: 9.5, fontWeight: 700, color: "rgba(255,255,255,0.3)", letterSpacing: 0.8, textTransform: "uppercase", marginBottom:6 }}>
            Password
          </label>
          <input
            type="password"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            style={{
              width: "100%", height: 46, background: "rgba(255,255,255,0.07)",
              border: "1px solid rgba(255,255,255,0.11)", borderRadius: 12, padding: "0 14px",
              color: "#fff", fontSize: 13, marginBottom: 20, outline: "none", boxSizing: "border-box",
            }}
          />

          <button
            onClick={handleLogin}
            disabled={loading}
            style={{
              width: "100%", height: 46, borderRadius: 12, border: "none",
              background: "linear-gradient(135deg, #3B8FE8, #1D65C4)", color: "#fff",
              fontSize: 14, fontWeight: 700, cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.6 : 1, boxShadow: "0 4px 20px rgba(59,143,232,0.3)",
            }}
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </div>
      </div>
    </div>
  )
}
