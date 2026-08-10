/**
 * S23 — Activity log.
 *
 * Read-only by design. The backend exposes no write endpoint and must not: an
 * audit trail that the application can edit is not an audit trail.
 *
 * `actor_id === null` means a system actor (webhook, scheduler, AI engine), not
 * a missing value. Rendering it as "—" would erase the distinction between
 * "nobody knows who did this" and "the machine did it".
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { activityApi } from '../../lib/api'
import { hasRole } from '../../lib/rbac'
import { useAuth } from '../../lib/auth'
import { NoAccess } from '../../components/RequireRole'
import { ErrorState, SkeletonRows } from '../../components/DataState'
import type { ActivityEntityType } from '../../types/travel'

const ENTITIES: ActivityEntityType[] = ['lead', 'call', 'booking', 'package', 'payment_link', 'user']

export default function ActivityLogPage() {
  const { me } = useAuth()
  const [entity, setEntity] = useState<ActivityEntityType | ''>('')
  const [action, setAction] = useState('')

  const canView = hasRole(me?.user, 'manager')

  const logQ = useQuery({
    queryKey: ['activity', entity, action],
    queryFn: () =>
      activityApi.list({
        entity: entity || undefined,
        action: action.trim() || undefined,
        limit: 100,
      }),
    enabled: canView,
  })

  if (!canView) {
    return (
      <>
        <div className="topbar"><div className="page-title">Activity Log</div></div>
        <div className="content"><NoAccess what="the activity log" /></div>
      </>
    )
  }

  const rows = logQ.data ?? []

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Activity Log</div>
          <div className="page-sub">{rows.length} most recent entries</div>
        </div>
        <div className="toolbar">
          <select aria-label="Filter by entity type"
            className="input"
            value={entity}
            onChange={(e) => setEntity(e.target.value as ActivityEntityType | '')}
          >
            <option value="">All entities</option>
            {ENTITIES.map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
          <input
            className="input"
            placeholder="Exact action, e.g. call.takeover.full"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          />
        </div>
      </div>

      <div className="content">
        {logQ.isLoading ? (
          <SkeletonRows rows={8} height={40} />
        ) : logQ.isError ? (
          <ErrorState error={logQ.error} onRetry={() => logQ.refetch()} />
        ) : rows.length === 0 ? (
          <div className="state-block">
            <p className="state-title">No matching activity</p>
            <p className="state-reason">
              {entity || action
                ? 'Nothing matches these filters. Action is an exact match, not a prefix — try clearing it.'
                : 'Nothing has been recorded yet.'}
            </p>
          </div>
        ) : (
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Action</th>
                  <th>Entity</th>
                  <th>Actor</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="muted-count">{new Date(r.at).toLocaleString()}</td>
                    <td><code className="activity-action">{r.action}</code></td>
                    <td className="muted-count">
                      {r.entity_type}
                      {r.entity_id && <span className="muted-count"> · {r.entity_id.slice(0, 8)}</span>}
                    </td>
                    <td className="muted-count">
                      {/* null is "system", not "unknown". */}
                      {r.actor_id ? r.actor_id.slice(0, 8) : <em>system</em>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="panel-footnote">
              This log is append-only — there is no write or edit endpoint, by design.
            </p>
          </div>
        )}
      </div>
    </>
  )
}
