/**
 * S11 — call event timeline.
 *
 * This is the AUDIT view of a call: every takeover transition, sentiment
 * update and pipeline step the backend recorded, in order. Distinct from the
 * transcript (what was said) and from the WS feed (what is happening now).
 *
 * Fetched over REST, not WS: `event` frames are never broadcast (DEBT-15), so
 * polling is the only way to see new rows. The interval is stated rather than
 * hidden, since a stale audit trail that looks live is worse than an obviously
 * periodic one.
 *
 * Security note worth preserving: this endpoint used to leak across tenants —
 * `get_call_scoped` returns None rather than raising, and the route discarded
 * the result, so a guessed UUID returned another business's event log
 * including supervisor phone numbers. Fixed in Phase 3; the 404 path below is
 * what a correctly-scoped miss now looks like.
 */
import { useQuery } from '@tanstack/react-query'

import { callsApi } from '../../lib/api'
import { ErrorState, SkeletonRows } from '../../components/DataState'

const POLL_MS = 15000

/** Known values from migration 0005. The column is an unconstrained VARCHAR,
 *  so anything not listed here still renders — just without a friendly label. */
const EVENT_LABEL: Record<string, string> = {
  takeover_monitor: 'Supervisor started monitoring',
  takeover_barge: 'Supervisor joined the conversation',
  takeover_full: 'Human took over the call',
  takeover_release: 'Call handed back to the AI',
  sentiment_update: 'Sentiment scored',
  suggestion_generated: 'Suggestion generated',
  post_call_complete: 'Post-call pipeline finished',
}

function tone(eventType: string): string {
  if (eventType.startsWith('takeover_')) return 'evt-takeover'
  if (eventType === 'post_call_complete') return 'evt-done'
  return 'evt-info'
}

export default function CallEventsPanel({ callId }: { callId: string }) {
  const eventsQ = useQuery({
    queryKey: ['calls', callId, 'events'],
    queryFn: () => callsApi.events(callId),
    refetchInterval: POLL_MS,
  })

  const events = eventsQ.data ?? []

  return (
    <div className="card">
      <div className="card-head">
        <div className="t2">
          Event log
          <span className="muted-count"> · {events.length}</span>
        </div>
        <span className="muted-count">every {POLL_MS / 1000}s</span>
      </div>

      {eventsQ.isLoading ? (
        <SkeletonRows rows={3} height={34} />
      ) : eventsQ.isError ? (
        <ErrorState error={eventsQ.error} onRetry={() => eventsQ.refetch()} />
      ) : events.length === 0 ? (
        <p className="state-reason" style={{ margin: 0 }}>
          Nothing recorded for this call yet. Takeovers and pipeline steps appear here as they
          happen.
        </p>
      ) : (
        <ul className="event-list">
          {events.map((e) => (
            <li key={e.id} className={`event-item ${tone(e.event_type)}`}>
              <div className="event-head">
                <span className="event-label">
                  {EVENT_LABEL[e.event_type] ?? e.event_type}
                </span>
                <span className="event-time">
                  {new Date(e.created_at).toLocaleTimeString()}
                </span>
              </div>
              {/* actor_id null = the system did it, not "unknown". */}
              <span className="muted-count">
                {e.actor_id ? `by ${e.actor_id.slice(0, 8)}` : 'automated'}
              </span>
            </li>
          ))}
        </ul>
      )}

      <p className="panel-footnote">
        Polled, not streamed — the backend emits no <code>event</code> frames on the live feed
        (DEBT-15).
      </p>
    </div>
  )
}
