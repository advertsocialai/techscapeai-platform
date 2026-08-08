/**
 * S0 — Mission Control.
 *
 * Three independent queries, each with its OWN loading/error state. The
 * previous version gated the whole screen on `a.isLoading || b.isLoading ||
 * c.isLoading` and showed one banner for any failure, which meant a single slow
 * or broken query blanked three working panels. Per-panel states let the
 * operator see what did load.
 */
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { bookingsApi, callsApi, leadsApi, playbooksApi } from '../../lib/api'
import { formatMoney } from '../../lib/money'
import { ErrorState, Skeleton, SkeletonRows } from '../../components/DataState'

const PIPELINE = ['new', 'qualified', 'negotiating', 'booked', 'lost'] as const

function StatCard({
  label,
  value,
  sub,
  color,
  loading,
  failed,
}: {
  label: string
  value: string | number
  sub: string
  color?: string
  loading: boolean
  failed: boolean
}) {
  return (
    <div className="stat">
      <div className="t4" style={{ marginBottom: 8, color }}>{label}</div>
      {loading ? (
        <Skeleton height={30} width="60%" />
      ) : failed ? (
        <div className="stat-val stat-failed" title="This figure could not be loaded">—</div>
      ) : (
        <div className="stat-val" style={{ color }}>{value}</div>
      )}
      <div className="stat-label">{failed ? 'could not load' : sub}</div>
    </div>
  )
}

export default function MissionControlPage() {
  const leadsQ = useQuery({ queryKey: ['leads'], queryFn: () => leadsApi.list() })
  const bookingsQ = useQuery({ queryKey: ['bookings'], queryFn: () => bookingsApi.list() })
  const runsQ = useQuery({ queryKey: ['playbook-runs'], queryFn: () => playbooksApi.runs({ limit: 50 }) })
  const liveQ = useQuery({
    queryKey: ['calls', 'live'],
    queryFn: callsApi.live,
    refetchInterval: 10000,
  })

  const leads = leadsQ.data ?? []
  const bookings = bookingsQ.data ?? []
  const runs = runsQ.data ?? []
  const live = liveQ.data ?? []

  const hotLeads = leads.filter((l) => l.qualification === 'hot')

  // Bookings carry `grand_total_inr`, a legacy column name. Summing it is only
  // valid while every booking is in one currency — which is why the figure is
  // rendered through formatMoney with an explicit INR label rather than as a
  // bare number. A multi-currency rollup must come from the server's FX
  // snapshot (see the money module), never from arithmetic here.
  const totalRevenue = bookings.reduce((sum, b) => sum + (b.grand_total_inr || 0), 0)

  const byStatus = Object.fromEntries(
    PIPELINE.map((s) => [s, leads.filter((l) => l.status === s).length]),
  ) as Record<(typeof PIPELINE)[number], number>

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Mission Control</div>
          <div className="page-sub">GoGaga Holidays · live data from the TravelWorkflow OS</div>
        </div>
      </div>

      <div className="content">
        <div className="grid-4" style={{ marginBottom: 18 }}>
          <StatCard
            label="Total Leads"
            value={leads.length}
            sub="in the funnel"
            loading={leadsQ.isLoading}
            failed={leadsQ.isError}
          />
          <StatCard
            label="Hot Leads"
            value={hotLeads.length}
            sub="ready to convert"
            color="var(--amber)"
            loading={leadsQ.isLoading}
            failed={leadsQ.isError}
          />
          <StatCard
            label="Booked Revenue"
            value={formatMoney(totalRevenue, 'INR')}
            sub={`${bookings.length} bookings`}
            color="var(--green)"
            loading={bookingsQ.isLoading}
            failed={bookingsQ.isError}
          />
          <StatCard
            label="Playbook Sends"
            value={runs.length}
            sub="automated dispatches"
            color="var(--blue)"
            loading={runsQ.isLoading}
            failed={runsQ.isError}
          />
        </div>

        {/* Live calls first: it is the only panel where being seconds out of
            date actually costs something. */}
        <div className="card" style={{ marginBottom: 18 }}>
          <div className="card-head">
            <div className="t2">
              Live Calls
              {live.length > 0 && <span className="badge live"> ● {live.length}</span>}
            </div>
            <Link className="btn ghost" to="/live-call">Open monitor →</Link>
          </div>

          {liveQ.isLoading ? (
            <SkeletonRows rows={2} height={44} />
          ) : liveQ.isError ? (
            <ErrorState error={liveQ.error} onRetry={() => liveQ.refetch()} />
          ) : live.length === 0 ? (
            <p className="state-reason" style={{ margin: 0 }}>
              No calls in progress right now.
            </p>
          ) : (
            <ul className="live-mini-list">
              {live.slice(0, 5).map((c) => (
                <li key={c.id}>
                  <Link to={`/live-call/${c.id}`} className="live-mini-item">
                    <span className="badge live">● live</span>
                    <span>{c.provider_sid ?? c.id.slice(0, 8)}</span>
                    <span className="muted-count">{c.language} · {c.mode}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          <div className="card-head">
            <div className="t2">Pipeline Snapshot</div>
            <Link className="btn ghost" to="/journey-board">View Journey Board →</Link>
          </div>

          {leadsQ.isLoading ? (
            <SkeletonRows rows={1} height={70} />
          ) : leadsQ.isError ? (
            <ErrorState error={leadsQ.error} onRetry={() => leadsQ.refetch()} />
          ) : (
            <div className="pipeline-row">
              {PIPELINE.map((s) => (
                <div key={s} className="pipeline-cell">
                  <div className="pipeline-count">{byStatus[s]}</div>
                  <div className="t4">{s}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
