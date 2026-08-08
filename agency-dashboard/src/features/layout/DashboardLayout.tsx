import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../../lib/auth'

const NAV_SECTIONS: { label: string; items: { to: string; label: string }[] }[] = [
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
      { to: '/team', label: 'Team' },
      { to: '/activity', label: 'Activity Log' },
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
              {section.items.map((item) => (
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
              <div style={{ fontSize: 9, color: 'var(--text-dim)' }}>{me?.user.role}</div>
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
