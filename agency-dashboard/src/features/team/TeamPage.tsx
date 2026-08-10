/**
 * S22 — Team. The user list, with create and deactivate.
 *
 * DELETE deactivates rather than destroys, and the button says so. Naming a
 * reversible action "Delete" makes people avoid it, or expect data to be gone
 * that is not.
 *
 * Role gating here is a UX affordance ONLY. The server re-reads the caller's
 * row on every request and ignores the token's role claim, so hiding this
 * screen from an agent stops an accidental click — it is not what makes user
 * management secure.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { usersApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { hasRole, roleLabel } from '../../lib/rbac'
import { useAuth } from '../../lib/auth'
import { NoAccess } from '../../components/RequireRole'
import { ErrorState, SkeletonRows } from '../../components/DataState'

/** Stored values, not spec vocabulary — see lib/rbac.ts for why they differ. */
const ASSIGNABLE_ROLES = [
  { value: 'viewer', label: 'Viewer — read only' },
  { value: 'agent', label: 'Agent — own leads' },
  { value: 'manager', label: 'Admin — whole business' },
]

export default function TeamPage() {
  const { me } = useAuth()
  const queryClient = useQueryClient()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('agent')
  const [error, setError] = useState<string | null>(null)

  const canManage = hasRole(me?.user, 'manager')

  const usersQ = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list({ limit: 100 }),
    enabled: canManage,
  })

  const create = useMutation({
    mutationFn: () => usersApi.create({ email: email.trim(), password, role }),
    onMutate: () => setError(null),
    onSuccess: () => {
      setEmail('')
      setPassword('')
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const deactivate = useMutation({
    mutationFn: (id: string) => usersApi.deactivate(id),
    onMutate: () => setError(null),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
    onError: (err) => setError(errorMessage(err)),
  })

  const reactivate = useMutation({
    mutationFn: (id: string) => usersApi.update(id, { status: 'active' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
    onError: (err) => setError(errorMessage(err)),
  })

  if (!canManage) {
    return (
      <>
        <div className="topbar"><div className="page-title">Team</div></div>
        <div className="content"><NoAccess what="team management" /></div>
      </>
    )
  }

  const users = usersQ.data?.items ?? []

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Team</div>
          <div className="page-sub">{usersQ.data?.total ?? 0} users</div>
        </div>
      </div>

      <div className="content">
        {error && <div className="error-banner" role="alert">{error}</div>}

        <div className="card" style={{ marginBottom: 16 }}>
          <div className="t2" style={{ marginBottom: 12 }}>Invite a user</div>
          <div className="form-row">
            <input
              className="input grow"
              type="email"
              placeholder="email@agency.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <input
              className="input"
              type="password"
              placeholder="Initial password (min 8)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <select aria-label="Role for new member" className="input" value={role} onChange={(e) => setRole(e.target.value)}>
              {ASSIGNABLE_ROLES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
            <button
              type="button"
              className="btn"
              disabled={!email.trim() || password.length < 8 || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? 'Creating…' : 'Create'}
            </button>
          </div>
          <p className="panel-footnote">
            The label "Admin" is stored as <code>manager</code>. The stored value <code>admin</code>
            {' '}means platform super-admin and is deliberately not assignable from here.
          </p>
        </div>

        {usersQ.isLoading ? (
          <SkeletonRows rows={5} height={48} />
        ) : usersQ.isError ? (
          <ErrorState error={usersQ.error} onRetry={() => usersQ.refetch()} />
        ) : users.length === 0 ? (
          <div className="state-block">
            <p className="state-title">No users</p>
            <p className="state-reason">Invite someone above.</p>
          </div>
        ) : (
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Last login</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const isSelf = u.id === me?.user.id
                  return (
                    <tr key={u.id} className={u.status === 'active' ? '' : 'row-archived'}>
                      <td>
                        {[u.first_name, u.last_name].filter(Boolean).join(' ') || u.email}
                        {isSelf && <span className="muted-count"> (you)</span>}
                      </td>
                      <td className="muted-count">{roleLabel(u.role)}</td>
                      <td>
                        <span className={`badge ${u.status === 'active' ? 'qual-converted' : 'qual-lost'}`}>
                          {u.status}
                        </span>
                      </td>
                      <td className="muted-count">
                        {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : 'never'}
                      </td>
                      <td>
                        {/* Locking yourself out is the classic own-goal here. */}
                        {isSelf ? (
                          <span className="muted-count">—</span>
                        ) : u.status === 'active' ? (
                          <button
                            type="button"
                            className="btn-secondary sm"
                            disabled={deactivate.isPending}
                            onClick={() => deactivate.mutate(u.id)}
                          >
                            Deactivate
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn-secondary sm"
                            disabled={reactivate.isPending}
                            onClick={() => reactivate.mutate(u.id)}
                          >
                            Reactivate
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <p className="panel-footnote">
              Deactivating suspends access and keeps the record — nothing is destroyed here.
            </p>
          </div>
        )}
      </div>
    </>
  )
}
