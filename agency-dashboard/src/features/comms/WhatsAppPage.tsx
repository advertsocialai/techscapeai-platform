/**
 * S13 — WhatsApp send + outbox.
 *
 * 💬 This screen can message a real person.
 *
 * Two backend behaviours drive the whole design, and neither is cosmetic:
 *
 * 1. STUB MODE. Without credentials the backend records the row and transmits
 *    nothing — `status: 'stubbed'`, `provider: 'stub'`. The row looks like a
 *    success in every other respect, so the outbox marks stubbed entries
 *    loudly. Confusing "recorded" for "delivered" is how someone concludes a
 *    customer was told something they were never told.
 *
 * 2. THE 24-HOUR WINDOW. WhatsApp only permits free-form text within 24 hours
 *    of the customer's last inbound message. Outside it the backend returns
 *    409 and an approved template is required. The form explains this BEFORE
 *    the send rather than surfacing it as a mystery error afterwards.
 *
 * Note the window state is tracked in an in-process dict (DEBT-10), so under
 * multiple workers one worker can refuse what another would allow. It fails
 * closed, which is the safe direction, but it means a 409 here is not
 * necessarily proof the window is shut.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { whatsappApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { isReadOnly } from '../../lib/rbac'
import { useAuth } from '../../lib/auth'
import { ErrorState, SkeletonRows } from '../../components/DataState'
import type { WhatsAppMessageType } from '../../types/travel'

export default function WhatsAppPage() {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const readOnly = isReadOnly(me?.user)

  const [to, setTo] = useState('')
  const [type, setType] = useState<WhatsAppMessageType>('template')
  const [templateName, setTemplateName] = useState('')
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<string | null>(null)

  const outboxQ = useQuery({
    queryKey: ['whatsapp', 'outbox'],
    queryFn: () => whatsappApi.outbox({ limit: 50 }),
  })

  const send = useMutation({
    mutationFn: () =>
      whatsappApi.send({
        to: to.trim(),
        message_type: type,
        template_name: type === 'template' ? templateName.trim() : null,
        text: type === 'freeform' ? text.trim() : null,
      }),
    onMutate: () => {
      setError(null)
      setLastResult(null)
    },
    onSuccess: (row) => {
      // Report what ACTUALLY happened, not "sent". The distinction between
      // transmitted and merely recorded is the whole point.
      setLastResult(
        row.status === 'stubbed' || row.provider === 'stub'
          ? `Recorded in the outbox only — provider "${row.provider}" transmitted nothing.`
          : `Handed to ${row.provider} with status "${row.status}".`,
      )
      setText('')
      queryClient.invalidateQueries({ queryKey: ['whatsapp', 'outbox'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const entries = outboxQ.data?.items ?? []
  const stubbedCount = entries.filter((e) => e.status === 'stubbed').length

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">WhatsApp</div>
          <div className="page-sub">
            {outboxQ.data ? `${outboxQ.data.total} messages in the outbox` : 'Loading…'}
          </div>
        </div>
      </div>

      <div className="content">
        {stubbedCount > 0 && (
          <div className="mode-banner stub" role="status">
            <strong>STUB MODE</strong>
            <span>
              {stubbedCount} of the {entries.length} messages shown were recorded but never
              transmitted. No WhatsApp credentials are configured.
            </span>
          </div>
        )}

        {error && <div className="error-banner" role="alert">{error}</div>}

        {!readOnly && (
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="t2" style={{ marginBottom: 12 }}>Send</div>

            <div className="form-row">
              <input
                className="input"
                placeholder="+919999900001 or 10-digit"
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
              <select aria-label="Message type"
                className="input"
                value={type}
                onChange={(e) => setType(e.target.value as WhatsAppMessageType)}
              >
                <option value="template">Template</option>
                <option value="freeform">Free-form</option>
              </select>
            </div>

            {type === 'template' ? (
              <input
                className="input full"
                placeholder="Approved template name"
                value={templateName}
                onChange={(e) => setTemplateName(e.target.value)}
              />
            ) : (
              <textarea
                className="input full"
                rows={3}
                placeholder="Message text"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            )}

            {/* Said before the attempt, not after the 409. */}
            {type === 'freeform' && (
              <p className="takeover-note warn">
                Free-form is only permitted within 24 hours of the customer's last inbound message.
                Outside that window the send is refused and an approved template is required.
              </p>
            )}

            <button
              type="button"
              className="btn"
              style={{ marginTop: 10 }}
              disabled={
                send.isPending ||
                !to.trim() ||
                (type === 'template' ? !templateName.trim() : !text.trim())
              }
              onClick={() => send.mutate()}
            >
              {send.isPending ? 'Sending…' : 'Send'}
            </button>

            {lastResult && <p className="takeover-note">{lastResult}</p>}
          </div>
        )}

        {outboxQ.isLoading ? (
          <SkeletonRows rows={5} height={48} />
        ) : outboxQ.isError ? (
          <ErrorState error={outboxQ.error} onRetry={() => outboxQ.refetch()} />
        ) : entries.length === 0 ? (
          <div className="state-block">
            <p className="state-title">Outbox is empty</p>
            <p className="state-reason">No WhatsApp messages have been queued yet.</p>
          </div>
        ) : (
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>To</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Provider</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id}>
                    <td>{e.to_number}</td>
                    <td className="muted-count">
                      {e.template_name ? `${e.message_type}: ${e.template_name}` : e.message_type}
                    </td>
                    <td><span className={`badge wa-${e.status}`}>{e.status}</span></td>
                    <td className="muted-count">{e.provider}</td>
                    <td className="muted-count">
                      {e.sent_at || e.created_at
                        ? new Date((e.sent_at ?? e.created_at)!).toLocaleString()
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
