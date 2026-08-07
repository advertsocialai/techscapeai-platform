import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { leadsApi } from '../../lib/api'
import type { Lead, LeadStatus } from '../../types/travel'

const COLUMNS: { status: LeadStatus; label: string; color: string }[] = [
  { status: 'new', label: 'New', color: 'var(--blue)' },
  { status: 'qualified', label: 'Qualified', color: 'var(--amber)' },
  { status: 'negotiating', label: 'Negotiating', color: 'var(--red)' },
  { status: 'booked', label: 'Booked', color: 'var(--green)' },
  { status: 'lost', label: 'Lost', color: 'rgba(255,255,255,0.4)' },
]

function formatInr(n: number | null) {
  if (!n) return '—'
  return `₹${n.toLocaleString('en-IN')}`
}

export default function JourneyBoardPage() {
  const navigate = useNavigate()
  const { data: leads, isLoading, isError } = useQuery({ queryKey: ['leads'], queryFn: () => leadsApi.list() })

  const grouped: Record<LeadStatus, Lead[]> = {
    new: [], qualified: [], itinerary_sent: [], negotiating: [], booked: [], lost: [],
  }
  for (const lead of leads ?? []) {
    grouped[lead.status]?.push(lead)
  }

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Journey Board</div>
          <div className="page-sub">{leads?.length ?? 0} total leads</div>
        </div>
      </div>
      <div className="content">
        {isLoading && <div className="loading-block">Loading…</div>}
        {isError && <div className="error-banner">Could not load leads.</div>}
        {!isLoading && !isError && (
          <div className="kanban">
            {COLUMNS.map((col) => (
              <div className="kan-col" key={col.status}>
                <div className="kan-header">
                  <span style={{ fontSize: 11, fontWeight: 700, color: col.color }}>{col.label.toUpperCase()}</span>
                  <div className="badge white">{grouped[col.status].length}</div>
                </div>
                {grouped[col.status].length === 0 && (
                  <div style={{ fontSize: 11, color: 'var(--text-xs)', padding: '8px 2px' }}>No leads</div>
                )}
                {grouped[col.status].map((lead) => (
                  <div className="kan-card" key={lead.id} onClick={() => navigate(`/journey-board/${lead.id}`)}>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 3 }}>
                      {lead.destination_hint || 'Unspecified destination'}
                    </div>
                    <div className="t3" style={{ fontSize: 10, marginBottom: 5 }}>
                      {formatInr(lead.budget_inr)} · {lead.pax_count ?? '?'} pax
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span className={`badge ${lead.qualification === 'hot' ? 'red' : lead.qualification === 'warm' ? 'amber' : 'white'}`} style={{ fontSize: 9 }}>
                        {lead.qualification}
                      </span>
                      <span className="t3" style={{ fontSize: 9 }}>score {lead.score}</span>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
