import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { leadsApi, bookingsApi, playbooksApi } from '../../lib/api'

function formatInr(n: number) {
  return `₹${n.toLocaleString('en-IN')}`
}

export default function MissionControlPage() {
  const leadsQ = useQuery({ queryKey: ['leads'], queryFn: () => leadsApi.list() })
  const bookingsQ = useQuery({ queryKey: ['bookings'], queryFn: () => bookingsApi.list() })
  const runsQ = useQuery({ queryKey: ['playbook-runs'], queryFn: () => playbooksApi.runs({ limit: 50 }) })

  const leads = leadsQ.data ?? []
  const bookings = bookingsQ.data ?? []
  const runs = runsQ.data ?? []

  const hotLeads = leads.filter((l) => l.qualification === 'hot')
  const totalRevenue = bookings.reduce((sum, b) => sum + (b.grand_total_inr || 0), 0)
  const byStatus = {
    new: leads.filter((l) => l.status === 'new').length,
    qualified: leads.filter((l) => l.status === 'qualified').length,
    negotiating: leads.filter((l) => l.status === 'negotiating').length,
    booked: leads.filter((l) => l.status === 'booked').length,
    lost: leads.filter((l) => l.status === 'lost').length,
  }

  const loading = leadsQ.isLoading || bookingsQ.isLoading || runsQ.isLoading
  const failed = leadsQ.isError || bookingsQ.isError || runsQ.isError

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Mission Control</div>
          <div className="page-sub">GoGaga Holidays · live data from the TravelWorkflow OS</div>
        </div>
      </div>
      <div className="content">
        {loading && <div className="loading-block">Loading…</div>}
        {failed && <div className="error-banner">Could not load dashboard data. Is the backend reachable?</div>}
        {!loading && !failed && (
          <>
            <div className="grid-4" style={{ marginBottom: 18 }}>
              <div className="stat">
                <div className="t4" style={{ marginBottom: 8 }}>Total Leads</div>
                <div className="stat-val">{leads.length}</div>
                <div className="stat-label">in the funnel</div>
              </div>
              <div className="stat">
                <div className="t4" style={{ marginBottom: 8, color: 'var(--amber)' }}>Hot Leads</div>
                <div className="stat-val" style={{ color: 'var(--amber)' }}>{hotLeads.length}</div>
                <div className="stat-label">ready to convert</div>
              </div>
              <div className="stat">
                <div className="t4" style={{ marginBottom: 8, color: 'var(--green)' }}>Booked Revenue</div>
                <div className="stat-val" style={{ color: 'var(--green)' }}>{formatInr(totalRevenue)}</div>
                <div className="stat-label">{bookings.length} bookings</div>
              </div>
              <div className="stat">
                <div className="t4" style={{ marginBottom: 8, color: 'var(--blue)' }}>Playbook Sends</div>
                <div className="stat-val" style={{ color: 'var(--blue)' }}>{runs.length}</div>
                <div className="stat-label">automated dispatches</div>
              </div>
            </div>

            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div className="t2">Pipeline Snapshot</div>
                <Link className="btn ghost" to="/journey-board">View Journey Board →</Link>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10 }}>
                {(['new', 'qualified', 'negotiating', 'booked', 'lost'] as const).map((s) => (
                  <div key={s} style={{ textAlign: 'center', padding: 12, background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 10 }}>
                    <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>{byStatus[s]}</div>
                    <div className="t4">{s}</div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  )
}
