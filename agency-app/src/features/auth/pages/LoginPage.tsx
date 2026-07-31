import { useState } from "react"
import { authApi } from "../../../lib/api"
import KlaraLogo from "../../../components/KlaraLogo"
import EyeIcon from "../../../components/EyeIcon"

interface LoginPageProps {
  onLoginSuccess: () => void
}

export default function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function handleLogin() {
    if (!email || !password) {
      setError("Please enter your email and password")
      return
    }
    setError("")
    setLoading(true)
    try {
      const res = await authApi.login({ email, password })
      localStorage.setItem("agency_access_token", res.data.access_token)
      onLoginSuccess()
    } catch (err: any) {
      setError(err.response?.data?.detail || "Invalid email or password")
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleLogin()
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "24px 20px",
    }}>
      {/* Ambient glows */}
      <div style={{ position: "fixed", top: -140, right: -100, width: 420, height: 420, borderRadius: "50%", background: "radial-gradient(circle, rgba(59,143,232,0.09) 0%, transparent 65%)", pointerEvents: "none", zIndex: 0 }} />
      <div style={{ position: "fixed", bottom: -120, left: -80, width: 360, height: 360, borderRadius: "50%", background: "radial-gradient(circle, rgba(247,169,124,0.07) 0%, transparent 65%)", pointerEvents: "none", zIndex: 0 }} />

      {/* Form column */}
      <div style={{ width: "100%", maxWidth: 430, position: "relative", zIndex: 1 }}>

        {/* Logo */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, marginBottom: 28 }}>
          <KlaraLogo />
          <div style={{ fontSize: 26, fontWeight: 800, color: "#fff", letterSpacing: -0.5 }}>Klara</div>
          <div style={{ fontSize: 9.5, fontWeight: 600, color: "rgba(247,169,124,0.6)", letterSpacing: 1.8, textTransform: "uppercase" }}>
            Agency Dashboard
          </div>
        </div>

        {/* Glass card */}
        <div style={{
          background: "rgba(255,255,255,0.06)",
          border: "1px solid rgba(255,255,255,0.11)",
          borderRadius: 28,
          padding: "28px 24px 26px",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06), 0 24px 64px rgba(0,0,0,0.35)",
          backdropFilter: "blur(20px)",
        }}>
          <div style={{ fontSize: 22, fontWeight: 800, color: "#fff", letterSpacing: -0.3, marginBottom: 4 }}>Welcome back</div>
          <div style={{ fontSize: 13, color: "rgba(255,255,255,0.42)", marginBottom: 24 }}>Sign in to your workspace</div>

          {/* Error */}
          {error && (
            <div style={{ background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.25)", borderRadius: 10, padding: "10px 14px", marginBottom: 16, fontSize: 12, color: "#F87171", display: "flex", alignItems: "center", gap: 8 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              {error}
            </div>
          )}

          {/* Email */}
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: "block", fontSize: 9.5, fontWeight: 700, color: "rgba(255,255,255,0.28)", letterSpacing: 0.9, textTransform: "uppercase", marginBottom: 6 }}>Email</label>
            <div style={{ position: "relative" }}>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="you@company.com"
                autoComplete="email"
                style={{
                  width: "100%", height: 50,
                  background: email ? "rgba(59,143,232,0.06)" : "rgba(255,255,255,0.07)",
                  border: email ? "1px solid rgba(59,143,232,0.35)" : "1px solid rgba(255,255,255,0.11)",
                  borderRadius: 13, padding: "0 46px 0 16px",
                  fontSize: 14, color: "#fff", outline: "none",
                  transition: "all 0.18s",
                }}
              />
              <div style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", color: "rgba(255,255,255,0.28)" }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
              </div>
            </div>
          </div>

          {/* Password */}
          <div style={{ marginBottom: 8 }}>
            <label style={{ display: "block", fontSize: 9.5, fontWeight: 700, color: "rgba(255,255,255,0.28)", letterSpacing: 0.9, textTransform: "uppercase", marginBottom: 6 }}>Password</label>
            <div style={{ position: "relative" }}>
              <input
                type={showPw ? "text" : "password"}
                value={password}
                onChange={e => setPassword(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Enter your password"
                autoComplete="current-password"
                style={{
                  width: "100%", height: 50,
                  background: password ? "rgba(59,143,232,0.06)" : "rgba(255,255,255,0.07)",
                  border: password ? "1px solid rgba(59,143,232,0.35)" : "1px solid rgba(255,255,255,0.11)",
                  borderRadius: 13, padding: "0 46px 0 16px",
                  fontSize: showPw ? 14 : 16, color: "#fff", outline: "none",
                  letterSpacing: showPw ? 0 : 3,
                  transition: "all 0.18s",
                }}
              />
              <button
                onClick={() => setShowPw(!showPw)}
                style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "rgba(255,255,255,0.3)", display: "flex", alignItems: "center", padding: 4 }}
              >
                <EyeIcon open={showPw} />
              </button>
            </div>
          </div>

          {/* Forgot */}
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 20 }}>
            <span style={{ fontSize: 12, fontWeight: 500, color: "#F7A97C", cursor: "pointer" }}>Forgot password?</span>
          </div>

          {/* Sign in button */}
          <button
            onClick={handleLogin}
            disabled={loading}
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              width: "100%", height: 50, borderRadius: 14, border: "none",
              background: "linear-gradient(135deg, #3B8FE8, #1D65C4)",
              boxShadow: "0 4px 20px rgba(59,143,232,0.3)",
              fontSize: 14, fontWeight: 700, color: "#fff", cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.75 : 1,
              transition: "opacity 0.18s",
            }}
          >
            {loading ? (
              <>
                <div style={{ width: 16, height: 16, borderRadius: "50%", border: "2px solid rgba(255,255,255,0.25)", borderTopColor: "#fff", animation: "spin 0.65s linear infinite" }} />
                Signing in…
              </>
            ) : "Sign In →"}
          </button>

          {/* Footer note — invite-only, no public signup */}
          <div style={{ textAlign: "center", marginTop: 20, fontSize: 12, color: "rgba(255,255,255,0.28)" }}>
            Agency access is by invitation. Contact your admin for access.
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        input::placeholder { color: rgba(255,255,255,0.22); }
        input:focus { border-color: rgba(59,143,232,0.55) !important; background: rgba(59,143,232,0.07) !important; box-shadow: 0 0 0 3px rgba(59,143,232,0.12) !important; }
      `}</style>
    </div>
  )
}
