/**
 * Traveller app shell — header, stub banner, bottom tab bar.
 *
 * The stub banner is rendered by the SHELL rather than by each screen, so a new
 * screen cannot forget it. While `TRAVELLER_API_IS_STUBBED` is true, every
 * traveller surface carries the notice; flipping that one flag removes it
 * everywhere at once.
 */
import { NavLink, Outlet } from 'react-router-dom'

import { STUB_NOTICE, TRAVELLER_API_IS_STUBBED } from '../../lib/travellerApi'
import { colors, layout } from '../../styles/tokens'

const TABS = [
  { to: '/trip', label: 'Trip' },
  { to: '/trip/payments', label: 'Payments' },
  { to: '/trip/messages', label: 'Messages' },
]

export default function TripShell() {
  return (
    <div style={{ minHeight: '100vh', paddingBottom: 78 }}>
      <div style={{ maxWidth: layout.maxWidth, margin: '0 auto', padding: '24px 20px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <div
            style={{
              width: 34, height: 34, borderRadius: 10,
              background: colors.blueGrad,
              display: 'grid', placeItems: 'center',
              fontWeight: 800, fontSize: 15,
            }}
          >
            G
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700 }}>Your trip</div>
            <div style={{ fontSize: 11, color: colors.textSecondary }}>GoGaga Holidays</div>
          </div>
        </div>

        {TRAVELLER_API_IS_STUBBED && (
          <div
            role="status"
            style={{
              background: colors.salmonDim,
              border: `1px solid ${colors.salmonBorder}`,
              borderRadius: 14,
              padding: '10px 13px',
              marginBottom: 16,
            }}
          >
            <div style={{ fontSize: 11, fontWeight: 800, color: colors.salmon, letterSpacing: 0.6 }}>
              SAMPLE DATA
            </div>
            <div style={{ fontSize: 11, color: colors.textSecondary, lineHeight: 1.5, marginTop: 3 }}>
              {STUB_NOTICE}
            </div>
          </div>
        )}

        <main>
          <Outlet />
        </main>
      </div>

      <nav
        style={{
          position: 'fixed', bottom: 0, left: 0, right: 0,
          background: 'rgba(6,15,38,0.92)',
          backdropFilter: 'blur(18px)',
          borderTop: `1px solid ${colors.surfaceBorder}`,
          display: 'flex', justifyContent: 'center', gap: 4,
          padding: '10px 12px calc(10px + env(safe-area-inset-bottom))',
        }}
      >
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.to === '/trip'}
            style={({ isActive }) => ({
              flex: 1, maxWidth: 130, textAlign: 'center',
              padding: '9px 0', borderRadius: 11,
              fontSize: 12, fontWeight: 600, textDecoration: 'none',
              color: isActive ? colors.blue : colors.textSecondary,
              background: isActive ? colors.blueDim : 'transparent',
            })}
          >
            {t.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
