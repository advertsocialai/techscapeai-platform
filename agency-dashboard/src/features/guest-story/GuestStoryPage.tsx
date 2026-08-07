import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { leadsApi, customersApi } from '../../lib/api'
import type { LeadStatus } from '../../types/travel'

const STATUS_OPTIONS: LeadStatus[] = ['new', 'qualified', 'itinerary_sent', 'negotiating', 'booked', 'lost']

function formatInr(n: number | null) {
  if (!n) return '—'
  return `₹${n.toLocaleString('en-IN')}`
}

export default function GuestStoryPage() {
  const { leadId } = useParams<{ leadId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const leadQ = useQuery({
    queryKey: ['lead', leadId],
    queryFn: () => leadsApi.get(leadId as string),
    enabled: !!leadId,
  })

  const customerQ = useQuery({
    queryKey: ['customer', leadQ.data?.customer_id],
    queryFn: () => customersApi.get(leadQ.data!.customer_id as string),
    enabled: !!leadQ.data?.customer_id,
  })

  const statusMutation = useMutation({
    mutationFn: (status: LeadStatus) => leadsApi.updateStatus(leadId as string, status),
    onSuccess: (updated) => {
      qc.setQueryData(['lead', leadId], updated)
      qc.invalidateQueries({ queryKey: ['leads'] })
    },
  })

  if (leadQ.isLoading) return <div className="loading-block">Loading…</div>
  if (leadQ.isError || !leadQ.data) return <div className="content"><div className="error-banner">Lead not found.</div></div>

  const lead = leadQ.data
  const customer = customerQ.data as { full_name?: string; email?: string; phone?: string } | undefined

  return (
    <>
      <div className="topbar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button className="btn ghost" onClick={() => navigate('/journey-board')}>← Back</button>
          <div>
            <div className="page-title">Guest Story {customer?.full_name ? `— ${customer.full_name}` : ''}</div>
            <div className="page-sub">Lead #{lead.id.slice(0, 8)} · via {lead.source}</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            value={lead.status}
            onChange={(e) => statusMutation.mutate(e.target.value as LeadStatus)}
            disabled={statusMutation.isPending}
            style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', borderRadius: 8, padding: '7px 10px', fontSize: 12 }}
          >
            {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>
      <div className="content">
        <div className="grid-2">
          <div>
            <div className="card" style={{ marginBottom: 14, background: 'rgba(16,185,129,0.05)', borderColor: 'var(--green-border)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <div className="t2">Lead Score</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--green)' }}>
                  {lead.score}<span style={{ fontSize: 13, color: 'var(--text-dim)' }}>/100</span>
                </div>
              </div>
              <span className={`badge ${lead.qualification === 'hot' ? 'red' : lead.qualification === 'warm' ? 'amber' : 'white'}`}>
                {lead.qualification}
              </span>
            </div>
            <div className="card">
              <div className="t2" style={{ marginBottom: 12 }}>Trip Details</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div><div className="t4" style={{ marginBottom: 4 }}>Destination</div><div>{lead.destination_hint || '—'}</div></div>
                <div><div className="t4" style={{ marginBottom: 4 }}>Budget</div><div>{formatInr(lead.budget_inr)}</div></div>
                <div><div className="t4" style={{ marginBottom: 4 }}>Pax</div><div>{lead.pax_count ?? '—'}</div></div>
                <div><div className="t4" style={{ marginBottom: 4 }}>Duration</div><div>{lead.duration_days ? `${lead.duration_days} days` : '—'}</div></div>
                <div><div className="t4" style={{ marginBottom: 4 }}>Phone</div><div>{customer?.phone || '—'}</div></div>
                <div><div className="t4" style={{ marginBottom: 4 }}>Email</div><div>{customer?.email || '—'}</div></div>
              </div>
            </div>
          </div>
          <div>
            <div className="card">
              <div className="t2" style={{ marginBottom: 10 }}>Original Message</div>
              <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.75)', lineHeight: 1.7 }}>
                "{lead.raw_message}"
              </div>
              {lead.intent && lead.intent !== lead.raw_message && (
                <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-dim)' }}>
                  Extracted intent: {lead.intent}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
