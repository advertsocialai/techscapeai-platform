/**
 * Assign a lead to an agent.
 *
 * NOT optimistic. Assignment changes who is accountable for a customer, and it
 * also changes RBAC scoping — an agent-tier user only sees leads assigned to
 * them, so a failed assignment that the UI showed as succeeded would leave the
 * operator believing a colleague can see a lead they cannot. That is a
 * different class of wrong from a kanban card in the wrong column.
 *
 * `Lead` carries no `assigned_agent` field in the REST shape, so the current
 * assignee cannot be displayed — the control shows what you are about to set,
 * not what is set. That gap is stated on screen rather than hidden behind a
 * blank select that implies "unassigned".
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { leadsApi, usersApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'

export default function AssignAgent({
  leadId,
  readOnly,
}: {
  leadId: string
  readOnly: boolean
}) {
  const queryClient = useQueryClient()
  const [choice, setChoice] = useState('')
  const [done, setDone] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const usersQ = useQuery({
    queryKey: ['users', 'assignable'],
    queryFn: () => usersApi.list({ status: 'active', limit: 100 }),
  })

  const assign = useMutation({
    mutationFn: (agentId: string | null) => leadsApi.assign(leadId, agentId),
    onMutate: () => {
      setError(null)
      setDone(null)
    },
    onSuccess: () => {
      setDone('Assignment saved.')
      queryClient.invalidateQueries({ queryKey: ['lead', leadId] })
      queryClient.invalidateQueries({ queryKey: ['leads'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const users = usersQ.data?.items ?? []

  return (
    <div className="card">
      <div className="t2" style={{ marginBottom: 12 }}>Assign</div>

      {readOnly ? (
        <p className="state-reason" style={{ margin: 0 }}>
          Your role is read-only, so leads cannot be reassigned.
        </p>
      ) : (
        <>
          <p className="panel-footnote" style={{ marginBottom: 10 }}>
            The current assignee is not shown — the lead API does not return one.
          </p>

          <select
            className="input"
            value={choice}
            disabled={usersQ.isLoading || assign.isPending}
            onChange={(e) => setChoice(e.target.value)}
            aria-label="Choose an agent"
          >
            <option value="">Unassign</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {[u.first_name, u.last_name].filter(Boolean).join(' ') || u.email} · {u.role}
              </option>
            ))}
          </select>

          <button
            type="button"
            className="btn"
            style={{ marginTop: 10, width: '100%' }}
            disabled={assign.isPending}
            onClick={() => assign.mutate(choice || null)}
          >
            {assign.isPending ? 'Saving…' : choice ? 'Assign' : 'Unassign'}
          </button>

          {usersQ.isError && (
            <p className="takeover-note warn">Could not load the agent list.</p>
          )}
          {done && <p className="takeover-note">{done}</p>}
          {error && <p className="takeover-note warn" role="alert">{error}</p>}
        </>
      )}
    </div>
  )
}
