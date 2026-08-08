/**
 * S12 — Payment links.
 *
 * 💰 This screen creates objects that can take money from a real customer.
 *
 * The single most important thing it renders is `gateway_mode`. When the
 * backend has no Razorpay credentials it runs in STUB mode: links are
 * `stub://`, the status machine works against real DB rows, and nothing can
 * ever be charged. An operator who does not know which mode they are in will
 * either send a dead link to a customer or believe a real charge was a test.
 * The banner is therefore not decoration — it is the primary content.
 *
 * Amounts are strings end-to-end. `PaymentLinkCreatePayload.amount` is typed as
 * string precisely so no float ever touches money; parsing to Number here to
 * "validate" would reintroduce exactly the representation this avoids.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { paymentsApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { formatMoney } from '../../lib/money'
import { isReadOnly } from '../../lib/rbac'
import { useAuth } from '../../lib/auth'
import { ErrorState, SkeletonRows } from '../../components/DataState'
import type { PaymentLinkStatus } from '../../types/travel'

/** Forward-only. `created` is absent because nothing transitions back INTO it. */
const NEXT_STATUS: Record<PaymentLinkStatus, PaymentLinkStatus[]> = {
  created: ['sent', 'expired'],
  sent: ['viewed', 'paid', 'expired'],
  viewed: ['paid', 'expired'],
  paid: [],
  expired: [],
}

export default function PaymentLinksPage() {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const readOnly = isReadOnly(me?.user)

  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState('INR')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)

  const linksQ = useQuery({
    queryKey: ['payment-links'],
    queryFn: () => paymentsApi.list({ limit: 50 }),
  })

  const create = useMutation({
    mutationFn: () =>
      paymentsApi.create({ amount: amount.trim(), currency, description: description.trim() }),
    onMutate: () => setError(null),
    onSuccess: () => {
      setAmount('')
      setDescription('')
      queryClient.invalidateQueries({ queryKey: ['payment-links'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const transition = useMutation({
    mutationFn: ({ id, status }: { id: string; status: PaymentLinkStatus }) =>
      paymentsApi.transition(id, { status: status as Exclude<PaymentLinkStatus, 'created'> }),
    onMutate: () => setError(null),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['payment-links'] }),
    onError: (err) => setError(errorMessage(err)),
  })

  const data = linksQ.data
  const isStub = data?.gateway_mode !== 'razorpay'

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Payment Links</div>
          <div className="page-sub">{data ? `${data.count} links` : 'Loading…'}</div>
        </div>
      </div>

      <div className="content">
        {/* Mode first, above everything. */}
        {data && (
          <div className={`mode-banner ${isStub ? 'stub' : 'live'}`} role="status">
            <strong>{isStub ? 'STUB MODE' : 'LIVE GATEWAY'}</strong>
            <span>
              {isStub
                ? `Gateway is "${data.gateway_mode}". Links are stub:// placeholders — nothing can be charged and no customer can pay one.`
                : 'Links created here are real and can take money from a real customer.'}
            </span>
          </div>
        )}

        {error && <div className="error-banner" role="alert">{error}</div>}

        {!readOnly && (
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="t2" style={{ marginBottom: 12 }}>Create a link</div>
            <div className="form-row">
              <input
                className="input"
                placeholder="Amount (major units, e.g. 45000)"
                inputMode="decimal"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
              <select
                className="input"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
              >
                <option value="INR">INR</option>
                <option value="USD">USD</option>
                <option value="CAD">CAD</option>
              </select>
              <input
                className="input grow"
                placeholder="Description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
              <button
                type="button"
                className="btn"
                disabled={!amount.trim() || create.isPending}
                onClick={() => create.mutate()}
              >
                {create.isPending ? 'Creating…' : 'Create'}
              </button>
            </div>
            <p className="panel-footnote">
              Amount is sent as text, never parsed to a float — money must not go through binary
              floating point.
            </p>
          </div>
        )}

        {linksQ.isLoading ? (
          <SkeletonRows rows={5} height={52} />
        ) : linksQ.isError ? (
          <ErrorState error={linksQ.error} onRetry={() => linksQ.refetch()} />
        ) : (data?.items.length ?? 0) === 0 ? (
          <div className="state-block">
            <p className="state-title">No payment links yet</p>
            <p className="state-reason">Create one above to get started.</p>
          </div>
        ) : (
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Gateway</th>
                  <th>Link</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data!.items.map((link) => (
                  <tr key={link.id}>
                    <td>{formatMoney(link.amount, link.currency, { maximumFractionDigits: 2 })}</td>
                    <td><span className={`badge pay-${link.status}`}>{link.status}</span></td>
                    <td className="muted-count">{link.gateway}</td>
                    <td>
                      {link.gateway_short_url ? (
                        // A stub:// URL is not clickable and must not pretend to be.
                        link.gateway_short_url.startsWith('stub://') ? (
                          <code className="stub-url">{link.gateway_short_url}</code>
                        ) : (
                          <a href={link.gateway_short_url} target="_blank" rel="noreferrer">
                            open ↗
                          </a>
                        )
                      ) : (
                        <span className="muted-count">—</span>
                      )}
                    </td>
                    <td className="muted-count">
                      {new Date(link.created_at).toLocaleDateString()}
                    </td>
                    <td>
                      {!readOnly && NEXT_STATUS[link.status].length > 0 && (
                        <select
                          className="kan-move"
                          value=""
                          aria-label="Advance status"
                          disabled={transition.isPending}
                          onChange={(e) =>
                            e.target.value &&
                            transition.mutate({
                              id: link.id,
                              status: e.target.value as PaymentLinkStatus,
                            })
                          }
                        >
                          <option value="">advance…</option>
                          {NEXT_STATUS[link.status].map((s) => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="panel-footnote">
              Status is forward-only. A paid link can never be demoted; an illegal transition is
              rejected with 409 rather than silently ignored.
            </p>
          </div>
        )}
      </div>
    </>
  )
}
