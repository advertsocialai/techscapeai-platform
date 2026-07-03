import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOnboarding } from '../context/OnboardingContext'

export default function SuccessPage() {
  const navigate = useNavigate()
  const { firstName, lastName, reset } = useOnboarding()

  // Clear onboarding state on mount
  useEffect(() => {
    return () => reset()
  }, [])

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '32px 20px',
    }}>
      {/* Ambient glows */}
      <div style={{ position: 'fixed', top: -140, right: -100, width: 420, height: 420, borderRadius: '50%', background: 'radial-gradient(circle, rgba(52,211,153,0.08) 0%, transparent 65%)', pointerEvents: 'none', zIndex: 0 }} />
      <div style={{ position: 'fixed', bottom: -120, left: -80, width: 360, height: 360, borderRadius: '50%', background: 'radial-gradient(circle, rgba(247,169,124,0.07) 0%, transparent 65%)', pointerEvents: 'none', zIndex: 0 }} />

      <div style={{ width: '100%', maxWidth: 430, position: 'relative', zIndex: 1 }}>
        <div style={{
          background: 'rgba(255,255,255,0.06)',
          border: '1px solid rgba(255,255,255,0.11)',
          borderRadius: 28,
          padding: '40px 28px',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06), 0 24px 64px rgba(0,0,0,0.35)',
          backdropFilter: 'blur(20px)',
          textAlign: 'center',
        }}>

          {/* Success ring */}
          <div style={{
            width: 94, height: 94, borderRadius: '50%',
            background: 'rgba(52,211,153,0.10)',
            border: '3px solid #34D399',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 20px',
            animation: 'pop 0.4s cubic-bezier(0.34,1.56,0.64,1)',
          }}>
            <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="#34D399" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20,6 9,17 4,12"/>
            </svg>
          </div>

          {/* Title */}
          <div style={{ fontSize: 32, fontWeight: 900, color: '#fff', letterSpacing: -1, marginBottom: 8 }}>
            You're in! 🌍
          </div>

          {/* Name */}
          <div style={{ fontSize: 16, fontWeight: 700, color: '#F7A97C', marginBottom: 6 }}>
            Welcome, {firstName} {lastName}
          </div>

          {/* Sub */}
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.42)', marginBottom: 28, lineHeight: 1.6 }}>
            Your Klara account is ready.<br/>
            Your AI travel concierge is standing by.
          </div>

          {/* What's next preview */}
          <div style={{
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 16, padding: 16, marginBottom: 24, textAlign: 'left',
          }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'rgba(255,255,255,0.25)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 14 }}>
              What's waiting for you
            </div>

            {[
              { icon: '💬', color: '#3B8FE8', bg: 'rgba(59,143,232,0.10)', border: 'rgba(59,143,232,0.25)', title: 'AI Chat Concierge', sub: 'Plan any trip in seconds' },
              { icon: '🎙️', color: '#F7A97C', bg: 'rgba(247,169,124,0.10)', border: 'rgba(247,169,124,0.25)', title: 'Voice AI in Telugu & Hindi', sub: 'Just speak — we handle the rest' },
              { icon: '✅', color: '#34D399', bg: 'rgba(52,211,153,0.10)', border: 'rgba(52,211,153,0.25)', title: 'Instant Booking', sub: 'Flights, hotels, packages — all in one' },
            ].map((item, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: i < 2 ? 12 : 0 }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 10, flexShrink: 0,
                  background: item.bg, border: `1px solid ${item.border}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 16,
                }}>
                  {item.icon}
                </div>
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#fff' }}>{item.title}</div>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{item.sub}</div>
                </div>
              </div>
            ))}
          </div>

          {/* CTA */}
          <button
            onClick={() => navigate('/dashboard')}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: '100%', height: 50, borderRadius: 14, border: 'none',
              background: 'linear-gradient(135deg, #F7A97C, #e07a3a)',
              boxShadow: '0 4px 20px rgba(247,169,124,0.25)',
              fontSize: 14, fontWeight: 700, color: '#fff', cursor: 'pointer',
              transition: 'opacity 0.18s',
            }}
            onMouseEnter={e => (e.currentTarget.style.opacity = '0.9')}
            onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
          >
            Start Exploring →
          </button>
        </div>
      </div>

      <style>{`
        @keyframes pop {
          from { transform: scale(0.6); opacity: 0; }
          to   { transform: scale(1);   opacity: 1; }
        }
      `}</style>
    </div>
  )
}
