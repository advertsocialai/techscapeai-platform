/**
 * S14 — Package catalogue.
 *
 * Delete is SOFT: the backend flips `is_active` to false and returns the
 * archived row. The UI says "Archive", not "Delete", because calling a
 * reversible action by a destructive name is how people avoid using it — or
 * worse, expect it to have removed data it did not.
 *
 * `base_price_inr` keeps a legacy column name but is NOT necessarily rupees —
 * `currency` says what it is. The two are always rendered together, which is
 * exactly the case the never-a-bare-amount rule exists for.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { packagesApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { formatMoney } from '../../lib/money'
import { isReadOnly } from '../../lib/rbac'
import { useAuth } from '../../lib/auth'
import { ErrorState, SkeletonRows } from '../../components/DataState'
import type { PackageCategory } from '../../types/travel'

const CATEGORIES: PackageCategory[] = ['budget', 'luxury', 'honeymoon', 'family']

export default function PackagesPage() {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const readOnly = isReadOnly(me?.user)

  const [showInactive, setShowInactive] = useState(false)
  const [category, setCategory] = useState<PackageCategory | ''>('')
  const [error, setError] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [days, setDays] = useState('')
  const [price, setPrice] = useState('')

  // Same rule as PaymentLinksPage: money and duration refuse junk before it
  // becomes a request. Empty = untouched (button disabled, no error shown).
  const daysValue = Number(days.trim())
  const daysValid = days.trim() !== '' && Number.isInteger(daysValue) && daysValue > 0
  // ge=0, not gt=0: the server model (packages.py base_price_inr Field(ge=0))
  // allows a zero-priced package, so the client must too — mirror, don't invent.
  const priceValue = Number(price.trim())
  const priceValid = price.trim() !== '' && Number.isFinite(priceValue) && priceValue >= 0
  const [currency, setCurrency] = useState('INR')
  const [newCategory, setNewCategory] = useState<PackageCategory | ''>('')

  const packagesQ = useQuery({
    queryKey: ['packages', showInactive, category],
    queryFn: () =>
      packagesApi.list({
        include_inactive: showInactive,
        category: category || undefined,
        limit: 100,
      }),
  })

  const create = useMutation({
    mutationFn: () =>
      packagesApi.create({
        name: name.trim(),
        duration_days: Number(days),
        base_price_inr: Number(price),
        currency,
        category: newCategory || null,
      }),
    onMutate: () => setError(null),
    onSuccess: () => {
      setName('')
      setDays('')
      setPrice('')
      queryClient.invalidateQueries({ queryKey: ['packages'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const archive = useMutation({
    mutationFn: (id: string) => packagesApi.remove(id),
    onMutate: () => setError(null),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['packages'] }),
    onError: (err) => setError(errorMessage(err)),
  })

  const restore = useMutation({
    mutationFn: (id: string) => packagesApi.update(id, { is_active: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['packages'] }),
    onError: (err) => setError(errorMessage(err)),
  })

  const packages = packagesQ.data ?? []

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Packages</div>
          <div className="page-sub">{packages.length} in the catalogue</div>
        </div>
        <div className="toolbar">
          <select aria-label="Filter by category"
            className="input"
            value={category}
            onChange={(e) => setCategory(e.target.value as PackageCategory | '')}
          >
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
            />
            Show archived
          </label>
        </div>
      </div>

      <div className="content">
        {error && <div className="error-banner" role="alert">{error}</div>}

        {!readOnly && (
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="t2" style={{ marginBottom: 12 }}>Add a package</div>
            <div className="form-row">
              <input className="input grow" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
              <input className="input" placeholder="Days" inputMode="numeric" aria-label="Duration in days" aria-invalid={days.trim() !== '' && !daysValid} value={days} onChange={(e) => setDays(e.target.value)} />
              <input className="input" placeholder="Price" inputMode="decimal" aria-label="Package price" aria-invalid={price.trim() !== '' && !priceValid} value={price} onChange={(e) => setPrice(e.target.value)} />
              {((days.trim() !== '' && !daysValid) || (price.trim() !== '' && !priceValid)) && (
                <span role="alert" style={{ color: 'var(--danger, #f87171)', fontSize: 12, alignSelf: 'center' }}>
                  {days.trim() !== '' && !daysValid ? 'Days must be a whole number above 0' : 'Price must be a number (0 or more)'}
                </span>
              )}
              <select aria-label="Currency" className="input" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                <option value="INR">INR</option>
                <option value="USD">USD</option>
                <option value="CAD">CAD</option>
              </select>
              <select aria-label="New package category"
                className="input"
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value as PackageCategory | '')}
              >
                <option value="">No category</option>
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <button
                type="button"
                className="btn"
                disabled={!name.trim() || !daysValid || !priceValid || create.isPending}
                onClick={() => create.mutate()}
              >
                {create.isPending ? 'Adding…' : 'Add'}
              </button>
            </div>
          </div>
        )}

        {packagesQ.isLoading ? (
          <SkeletonRows rows={5} height={52} />
        ) : packagesQ.isError ? (
          <ErrorState error={packagesQ.error} onRetry={() => packagesQ.refetch()} />
        ) : packages.length === 0 ? (
          <div className="state-block">
            <p className="state-title">No packages</p>
            <p className="state-reason">
              {category || !showInactive
                ? 'None match the current filters. Try clearing them or showing archived packages.'
                : 'The catalogue is empty. Add one above.'}
            </p>
          </div>
        ) : (
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Duration</th>
                  <th>Price</th>
                  <th>State</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {packages.map((p) => (
                  <tr key={p.id} className={p.is_active ? '' : 'row-archived'}>
                    <td>{p.name}</td>
                    <td className="muted-count">{p.category ?? '—'}</td>
                    <td className="muted-count">
                      {p.duration_days}d{p.nights != null ? ` / ${p.nights}n` : ''}
                    </td>
                    {/* Never the number alone — the column name says INR but the
                        currency field is what actually determines the unit. */}
                    <td>{formatMoney(p.base_price_inr, p.currency)}</td>
                    <td>
                      <span className={`badge ${p.is_active ? 'qual-converted' : 'qual-lost'}`}>
                        {p.is_active ? 'active' : 'archived'}
                      </span>
                    </td>
                    <td>
                      {!readOnly &&
                        (p.is_active ? (
                          <button
                            type="button"
                            className="btn-secondary sm"
                            disabled={archive.isPending}
                            onClick={() => archive.mutate(p.id)}
                          >
                            Archive
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn-secondary sm"
                            disabled={restore.isPending}
                            onClick={() => restore.mutate(p.id)}
                          >
                            Restore
                          </button>
                        ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="panel-footnote">
              Archiving is reversible — it flips <code>is_active</code> and keeps the row. No
              package data is ever destroyed from this screen.
            </p>
          </div>
        )}
      </div>
    </>
  )
}
