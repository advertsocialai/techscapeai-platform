/**
 * S2 — Guest Story. Everything known about one lead, on one screen.
 *
 * Assembled from four independent endpoints. Each renders its own state, so a
 * missing customer record does not blank the lead detail that loaded fine —
 * partial knowledge shown honestly beats an all-or-nothing error page.
 */
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { activityApi, callsApi, customersApi, leadsApi } from '../../lib/api'
import { formatMoney } from '../../lib/money'
import { isReadOnly } from '../../lib/rbac'
import { useAuth } from '../../lib/auth'
import { ErrorState, SkeletonRows } from '../../components/DataState'
import AssignAgent from './AssignAgent'

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="field-row">
      <span className="field-label">{label}</span>
      <span className="field-value">{value ?? <span className="muted-count">—</span>}</span>
    </div>
  )
}

export default function GuestStoryPage() {
  const { leadId } = useParams<{ leadId: string }>()
  const { me } = useAuth()
  const readOnly = isReadOnly(me?.user)

  const leadQ = useQuery({
    queryKey: ['lead', leadId],
    queryFn: () => leadsApi.get(leadId!),
    enabled: !!leadId,
  })

  const lead = leadQ.data

  const customerQ = useQuery({
    queryKey: ['customer', lead?.customer_id],
    queryFn: () => customersApi.get(lead!.customer_id!),
    enabled: !!lead?.customer_id,
  })

  const activityQ = useQuery({
    queryKey: ['activity', 'lead', leadId],
    queryFn: () => activityApi.list({ entity: 'lead', entity_id: leadId!, limit: 30 }),
    enabled: !!leadId,
  })

  // There is no "calls for this lead" endpoint, so this filters the live list.
  // It therefore only ever shows ACTIVE calls — stated in the panel rather than
  // left to look like "this lead has never been called".
  const liveQ = useQuery({ queryKey: ['calls', 'live'], queryFn: callsApi.live })
  const leadCalls = (liveQ.data ?? []).filter((c) => c.lead_id === leadId)

  if (!leadId) return <ErrorState error={new Error('No lead id in the URL')} />

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">
            <Link to="/journey-board" className="crumb">Journey Board</Link>
            <span className="crumb-sep">/</span>
            {lead?.destination_hint || lead?.intent || 'Guest Story'}
          </div>
          <div className="page-sub">
            {lead ? `${lead.status} · ${lead.qualification} · score ${lead.score}` : 'Loading…'}
          </div>
        </div>
      </div>

      <div className="content">
        {leadQ.isLoading ? (
          <SkeletonRows rows={5} height={48} />
        ) : leadQ.isError ? (
          <ErrorState error={leadQ.error} onRetry={() => leadQ.refetch()} />
        ) : !lead ? (
          <div className="state-block">
            <p className="state-title">Lead not found</p>
            <p className="state-reason">
              It may belong to another branch, or have been deleted.
            </p>
          </div>
        ) : (
          <div className="story-grid">
            <div className="story-main">
              <div className="card">
                <div className="t2" style={{ marginBottom: 12 }}>The ask</div>
                <p className="story-message">{lead.raw_message}</p>
                <div className="field-list">
                  <Field label="Destination" value={lead.destination_hint} />
                  <Field label="Intent" value={lead.intent} />
                  <Field label="Travellers" value={lead.pax_count} />
                  <Field label="Duration" value={lead.duration_days ? `${lead.duration_days} days` : null} />
                  <Field
                    label="Budget"
                    value={lead.budget_inr != null ? formatMoney(lead.budget_inr, 'INR') : null}
                  />
                  <Field label="Source" value={lead.source} />
                </div>
              </div>

              <div className="card">
                <div className="t2" style={{ marginBottom: 12 }}>Activity</div>
                {activityQ.isLoading ? (
                  <SkeletonRows rows={4} height={38} />
                ) : activityQ.isError ? (
                  <ErrorState error={activityQ.error} onRetry={() => activityQ.refetch()} />
                ) : (activityQ.data ?? []).length === 0 ? (
                  <p className="state-reason" style={{ margin: 0 }}>
                    Nothing recorded against this lead yet.
                  </p>
                ) : (
                  <ul className="activity-list">
                    {(activityQ.data ?? []).map((row) => (
                      <li key={row.id} className="activity-item">
                        <span className="activity-action">{row.action}</span>
                        <span className="activity-time">
                          {new Date(row.at).toLocaleString()}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            <aside className="story-side">
              <div className="card">
                <div className="t2" style={{ marginBottom: 12 }}>Guest</div>
                {!lead.customer_id ? (
                  <p className="state-reason" style={{ margin: 0 }}>
                    No customer record is linked to this lead yet.
                  </p>
                ) : customerQ.isLoading ? (
                  <SkeletonRows rows={3} height={30} />
                ) : customerQ.isError ? (
                  <ErrorState error={customerQ.error} onRetry={() => customerQ.refetch()} />
                ) : (
                  <div className="field-list">
                    <Field label="Name" value={(customerQ.data as { name?: string })?.name} />
                    <Field label="Phone" value={(customerQ.data as { phone?: string })?.phone} />
                    <Field label="Email" value={(customerQ.data as { email?: string })?.email} />
                  </div>
                )}
              </div>

              <AssignAgent leadId={lead.id} readOnly={readOnly} />

              <div className="card">
                <div className="t2" style={{ marginBottom: 12 }}>Calls</div>
                {leadCalls.length === 0 ? (
                  <p className="state-reason" style={{ margin: 0 }}>
                    No <strong>active</strong> calls for this lead. Past calls are not listed —
                    the backend exposes no per-lead call history endpoint.
                  </p>
                ) : (
                  <ul className="live-mini-list">
                    {leadCalls.map((c) => (
                      <li key={c.id}>
                        <Link to={`/live-call/${c.id}`} className="live-mini-item">
                          <span className="badge live">● live</span>
                          <span>{c.provider_sid ?? c.id.slice(0, 8)}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </aside>
          </div>
        )}
      </div>
    </>
  )
}
