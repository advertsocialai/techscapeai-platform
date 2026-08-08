/**
 * S25 — Empire. Branches and tenant-level view.
 *
 * 🏢 This screen deliberately does NOT onboard tenants, submit Plivo Reseller
 * applications, or issue invoices. Those are permanently human-gated actions
 * (BLOCKERS.md B-P5-03, B-P5-04) — not "not built yet", but "must not be
 * automated". The distinction is stated on screen so a future reader does not
 * treat the absence as a TODO and wire it up.
 *
 * Branch creation IS here: a branch is an internal subdivision of the
 * business you already own, not a new external business relationship.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { branchesApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { hasRole } from '../../lib/rbac'
import { useAuth } from '../../lib/auth'
import { NoAccess } from '../../components/RequireRole'
import { ErrorState, SkeletonRows } from '../../components/DataState'

export default function EmpirePage() {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const canManage = hasRole(me?.user, 'manager')

  const [name, setName] = useState('')
  const [city, setCity] = useState('')
  const [error, setError] = useState<string | null>(null)

  const branchesQ = useQuery({
    queryKey: ['branches'],
    queryFn: () => branchesApi.list({ limit: 100 }),
    enabled: canManage,
  })

  const create = useMutation({
    mutationFn: () => branchesApi.create({ name: name.trim(), city: city.trim() || null }),
    onMutate: () => setError(null),
    onSuccess: () => {
      setName('')
      setCity('')
      queryClient.invalidateQueries({ queryKey: ['branches'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (!canManage) {
    return (
      <>
        <div className="topbar"><div className="page-title">Empire</div></div>
        <div className="content"><NoAccess what="branch management" /></div>
      </>
    )
  }

  const branches = branchesQ.data?.items ?? []

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Empire</div>
          <div className="page-sub">
            {me?.name} · {branches.length} branch{branches.length === 1 ? '' : 'es'}
          </div>
        </div>
      </div>

      <div className="content">
        {error && <div className="error-banner" role="alert">{error}</div>}

        <div className="card" style={{ marginBottom: 16 }}>
          <div className="t2" style={{ marginBottom: 12 }}>Add a branch</div>
          <div className="form-row">
            <input
              className="input grow"
              placeholder="Branch name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <input
              className="input"
              placeholder="City"
              value={city}
              onChange={(e) => setCity(e.target.value)}
            />
            <button
              type="button"
              className="btn"
              disabled={!name.trim() || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? 'Adding…' : 'Add branch'}
            </button>
          </div>
          <p className="panel-footnote">
            A branch is a subdivision of your own business. It does not create a separate tenant.
          </p>
        </div>

        {branchesQ.isLoading ? (
          <SkeletonRows rows={3} height={48} />
        ) : branchesQ.isError ? (
          <ErrorState error={branchesQ.error} onRetry={() => branchesQ.refetch()} />
        ) : branches.length === 0 ? (
          <div className="state-block">
            <p className="state-title">No branches</p>
            <p className="state-reason">
              Everything runs under the business directly. Add a branch to scope leads, users and
              reports separately.
            </p>
          </div>
        ) : (
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>Branch</th>
                  <th>City</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {branches.map((b) => (
                  <tr key={b.id}>
                    <td>{b.name}</td>
                    <td className="muted-count">{b.city ?? '—'}</td>
                    <td>
                      <span className={`badge ${b.status === 'active' ? 'qual-converted' : 'qual-lost'}`}>
                        {b.status}
                      </span>
                    </td>
                    <td className="muted-count">{new Date(b.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Stated, not silently omitted. */}
        <div className="card" style={{ marginTop: 16 }}>
          <div className="t2" style={{ marginBottom: 10 }}>Deliberately not here</div>
          <p className="state-reason" style={{ marginBottom: 10 }}>
            These are not missing features. They are actions with real-world legal and financial
            consequences, and they require a human every time — no dashboard button should be able
            to trigger them.
          </p>
          <ul className="unavailable-list">
            <li>
              <strong>Tenant onboarding</strong> — creating a second business is a contractual act,
              not a form submission
            </li>
            <li>
              <strong>Plivo Reseller application</strong> — real KYC against a real company
              (B-P5-03)
            </li>
            <li>
              <strong>Invoicing a tenant</strong> — billing scaffolding exists in the schema;
              issuing a real charge is human-authorised every time (B-P5-04)
            </li>
          </ul>
        </div>
      </div>
    </>
  )
}
