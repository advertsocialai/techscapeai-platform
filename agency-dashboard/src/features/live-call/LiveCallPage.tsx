/**
 * S10 — Live Call Monitor. The list of currently-active calls.
 *
 * Polled rather than pushed: the WS feed is per-call (`/ws/calls/{id}`), so
 * there is no channel that announces a NEW call starting. Polling is the honest
 * mechanism here, and the interval is stated in the UI so nobody mistakes a
 * 5-second-old list for a live one.
 */
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { callsApi } from '../../lib/api'
import { ErrorState, SkeletonRows } from '../../components/DataState'
import type { Call } from '../../types/travel'

const POLL_MS = 5000

function duration(call: Call): string {
  if (call.duration_sec != null) return `${Math.floor(call.duration_sec / 60)}m ${call.duration_sec % 60}s`
  if (!call.started_at) return '—'
  const secs = Math.max(0, Math.floor((Date.now() - new Date(call.started_at).getTime()) / 1000))
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

export default function LiveCallPage() {
  const callsQ = useQuery({
    queryKey: ['calls', 'live'],
    queryFn: callsApi.live,
    refetchInterval: POLL_MS,
  })

  const calls = callsQ.data ?? []

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Live Calls</div>
          <div className="page-sub">
            Active calls across the business · refreshed every {POLL_MS / 1000}s
          </div>
        </div>
      </div>

      <div className="content">
        {callsQ.isLoading ? (
          <SkeletonRows rows={4} height={64} />
        ) : callsQ.isError ? (
          <ErrorState error={callsQ.error} onRetry={() => callsQ.refetch()} />
        ) : calls.length === 0 ? (
          <div className="state-block">
            <p className="state-title">No calls in progress</p>
            <p className="state-reason">
              This list shows calls with status <code>active</code>. It is empty because none are
              running right now — not because the connection failed.
            </p>
          </div>
        ) : (
          <div className="live-call-grid">
            {calls.map((call) => (
              <Link key={call.id} to={`/live-call/${call.id}`} className="card live-call-card">
                <div className="live-call-head">
                  <span className="badge live">● live</span>
                  <span className="live-call-lang">{call.language}</span>
                </div>
                <div className="live-call-id">{call.provider_sid ?? call.id.slice(0, 8)}</div>
                <div className="live-call-meta">
                  <span>{duration(call)}</span>
                  <span className="dot-sep">·</span>
                  <span>mode: {call.mode}</span>
                </div>
                {/* sentiment_score is an EMA of the intent dimension only, seeded
                    at 0.5 — see DEBT-07. Labelled rather than presented as an
                    overall sentiment, which it is not. */}
                {call.sentiment_score != null && (
                  <div className="live-call-sentiment">
                    intent trend {Math.round(call.sentiment_score * 100)}%
                  </div>
                )}
                <span className="live-call-open">Open monitor →</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
