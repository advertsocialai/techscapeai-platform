/**
 * S15 — Follow-up queue.
 *
 * `FollowUp` carries BOTH `status` and `stored_status`, and they are not
 * duplicates: `stored_status` is the row as written, while `status` is derived
 * at read time (a `due` row whose `due_at` has passed reads back as `overdue`).
 * Showing the derived one is right for the queue; showing them together when
 * they differ is what stops "why did this change on its own?".
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { followUpsApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { isReadOnly } from '../../lib/rbac'
import { useAuth } from '../../lib/auth'
import { ErrorState, SkeletonRows } from '../../components/DataState'
import type { FollowUpStatus } from '../../types/travel'
import LadderEditor from './LadderEditor'

const STATUSES: FollowUpStatus[] = ['due', 'overdue', 'in_progress', 'done']

function relative(iso: string): string {
  const diffMs = new Date(iso).getTime() - Date.now()
  const mins = Math.round(diffMs / 60000)
  const abs = Math.abs(mins)
  const unit = abs < 60 ? `${abs}m` : abs < 1440 ? `${Math.round(abs / 60)}h` : `${Math.round(abs / 1440)}d`
  return mins < 0 ? `${unit} overdue` : `in ${unit}`
}

export default function FollowUpsPage() {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const readOnly = isReadOnly(me?.user)

  const [filter, setFilter] = useState<FollowUpStatus | ''>('')
  const [error, setError] = useState<string | null>(null)

  const queueQ = useQuery({
    queryKey: ['follow-ups', filter],
    queryFn: () => followUpsApi.list({ status: filter || undefined, limit: 100 }),
  })

  const rulesQ = useQuery({ queryKey: ['follow-ups', 'rules'], queryFn: followUpsApi.rules })

  const update = useMutation({
    mutationFn: ({ id, status }: { id: string; status: FollowUpStatus }) =>
      followUpsApi.update(id, { status }),
    onMutate: () => setError(null),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['follow-ups'] }),
    onError: (err) => setError(errorMessage(err)),
  })

  const items = queueQ.data ?? []
  const overdue = items.filter((f) => f.status === 'overdue').length

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Follow-ups</div>
          <div className="page-sub">
            {items.length} in the queue
            {overdue > 0 && ` · ${overdue} overdue`}
          </div>
        </div>
        <div className="toolbar">
          <select
            className="input"
            value={filter}
            onChange={(e) => setFilter(e.target.value as FollowUpStatus | '')}
          >
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      <div className="content">
        {error && <div className="error-banner" role="alert">{error}</div>}

        {queueQ.isLoading ? (
          <SkeletonRows rows={6} height={48} />
        ) : queueQ.isError ? (
          <ErrorState error={queueQ.error} onRetry={() => queueQ.refetch()} />
        ) : items.length === 0 ? (
          <div className="state-block">
            <p className="state-title">Nothing to follow up</p>
            <p className="state-reason">
              {filter
                ? `No follow-ups with status "${filter}". Clear the filter to see the rest.`
                : 'The queue is empty. Ladders are scheduled automatically when a lead qualifies.'}
            </p>
          </div>
        ) : (
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>Lead</th>
                  <th>Day</th>
                  <th>Type</th>
                  <th>Channel</th>
                  <th>Due</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((f) => (
                  <tr key={f.id} className={f.status === 'overdue' ? 'row-overdue' : ''}>
                    <td>
                      <Link to={`/journey-board/${f.lead_id}`}>{f.lead_id.slice(0, 8)}</Link>
                    </td>
                    <td className="muted-count">D{f.ladder_day}</td>
                    <td className="muted-count">{f.type}</td>
                    <td className="muted-count">{f.channel}</td>
                    <td className="muted-count" title={new Date(f.due_at).toLocaleString()}>
                      {relative(f.due_at)}
                    </td>
                    <td>
                      <span className={`badge fu-${f.status}`}>{f.status}</span>
                      {/* Only surfaced when they disagree — otherwise it is noise. */}
                      {f.stored_status !== f.status && (
                        <span className="muted-count"> (stored: {f.stored_status})</span>
                      )}
                    </td>
                    <td>
                      {!readOnly && f.status !== 'done' && (
                        <button
                          type="button"
                          className="btn-secondary sm"
                          disabled={update.isPending}
                          onClick={() => update.mutate({ id: f.id, status: 'done' })}
                        >
                          Mark done
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="card" style={{ marginTop: 16 }}>
          <div className="t2" style={{ marginBottom: 12 }}>Ladder rules</div>
          {rulesQ.isLoading ? (
            <SkeletonRows rows={3} height={34} />
          ) : rulesQ.isError ? (
            <ErrorState error={rulesQ.error} onRetry={() => rulesQ.refetch()} />
          ) : (
            <LadderEditor rules={rulesQ.data?.ladder ?? []} readOnly={readOnly} />
          )}
        </div>
      </div>
    </>
  )
}
