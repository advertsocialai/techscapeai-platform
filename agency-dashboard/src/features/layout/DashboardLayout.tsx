import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../../lib/auth'
import { hasRole, roleLabel, type Role } from '../../lib/rbac'

/**
 * `minimum` hides a link the user's role cannot use. This is a UX affordance,
 * NOT access control — the server re-reads the caller's row and ignores the
 * token's role claim, so a hidden link is still reachable by typing the URL and
 * still correctly refused there. Hiding it just stops people clicking into a
 * guaranteed 403.
 */
type NavItem = { to: string; label: string; minimum?: Role }

const NAV_SECTIONS: { label: string; items: NavItem[] }[] = [
  {
    label: 'Main',
    items: [
      { to: '/', label: 'Mission Control' },
      { to: '/live-call', label: 'Live Call' },
    ],
  },
  {
    label: 'Leads',
    items: [
      { to: '/journey-board', label: 'Journey Board' },
    ],
  },
  {
    label: 'Revenue',
    items: [
      { to: '/bookings', label: 'Bookings' },
      { to: '/packages', label: 'Packages' },
      { to: '/payment-links', label: 'Payment Links' },
    ],
  },
  {
    label: 'Comms',
    items: [
      { to: '/whatsapp', label: 'WhatsApp' },
      { to: '/follow-ups', label: 'Follow-ups' },
    ],
  },
  {
    label: 'Insight',
    items: [
      { to: '/reports', label: 'Reports' },
      { to: '/cost', label: 'Cost & Revenue' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { to: '/playbooks', label: 'AI Playbook' },
      { to: '/ai-config', label: 'AI Config', minimum: 'manager' },
      { to: '/team', label: 'Team', minimum: 'manager' },
      { to: '/activity', label: 'Activity Log', minimum: 'manager' },
      { to: '/empire', label: 'Empire', minimum: 'manager' },
    ],
  },
]

export default function DashboardLayout() {
  const { me, logout } = useAuth()

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="mark">G</div>
          <div>
            <div className="name">GoGaga</div>
            <div className="sub">Agency Platform</div>
          </div>
        </div>
        <nav className="sidebar-nav">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label}>
              <div className="nav-section-label">{section.label}</div>
              {section.items
                .filter((item) => !item.minimum || hasRole(me?.user, item.minimum))
                .map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-pill">
            <div className="avatar">
              {(me?.user.first_name?.[0] ?? me?.user.email[0] ?? '?').toUpperCase()}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {me?.user.first_name || me?.user.email}
              </div>
              <div style={{ fontSize: 9, color: 'var(--text-dim)' }}>{roleLabel(me?.user.role)}</div>
            </div>
            <button
              className="btn ghost"
              style={{ marginLeft: 'auto', padding: '4px 8px' }}
              onClick={logout}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <div className="main">
        <Outlet />
      </div>
    </div>
  )
}
