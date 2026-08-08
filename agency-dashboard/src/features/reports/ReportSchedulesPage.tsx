/**
 * S26 — Scheduled report delivery.
 *
 * Three things here are load-bearing rather than cosmetic:
 *
 * 1. 💬 `runDue` DELIVERS REAL MESSAGES when `dry_run=false`. The server
 *    defaults it to TRUE, and this screen keeps that default and makes the
 *    distinction the loudest thing on the button. A "run" control that might
 *    or might not message real customers depending on an unseen default is a
 *    trap.
 *
 * 2. WhatsApp delivery is KNOWN BROKEN, and correctly so (B-P4-07). A
 *    scheduled report is unsolicited, so it falls outside WhatsApp's 24-hour
 *    customer-service window and `send_freeform` refuses it. That needs a
 *    Meta-approved template — calendar time, not engineering time. Stated up
 *    front so nobody debugs a working refusal.
 *
 * 3. Email delivery returns `unavailable` — no mail transport is wired
 *    (B-P4-08). The channel selector says so at the point of choosing.
 *
 * `send_time` is a LOCAL wall clock in the schedule's own timezone, not a UTC
 * instant. Rendering it as a UTC time would be wrong twice a year.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { reportsApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { hasRole } from '../../lib/rbac'
import { useAuth } from '../../lib/auth'
import { NoAccess } from '../../components/RequireRole'
import { ErrorState, SkeletonRows } from '../../components/DataState'
import type { ReportDeliveryChannel, ReportType } from '../../types/travel'

const TYPES: ReportType[] = ['daily', 'weekly', 'monthly']

export default function ReportSchedulesPage() {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const canManage = hasRole(me?.user, 'manager')

  const [reportType, setReportType] = useState<ReportType>('daily')
  const [channel, setChannel] = useState<ReportDeliveryChannel>('whatsapp')
  const [sendTime, setSendTime] = useState('09:00')
  const [recipients, setRecipients] = useState('')
  const [timezone, setTimezone] = useState('Asia/Kolkata')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const schedulesQ = useQuery({
    queryKey: ['report-schedules'],
    queryFn: () => reportsApi.listSchedules({ limit: 50 }),
    enabled: canManage,
  })

  const dueQ = useQuery({
    queryKey: ['report-schedules', 'due'],
    queryFn: () => reportsApi.scheduledDue({ include_skipped: true }),
    enabled: canManage,
  })

  const create = useMutation({
    mutationFn: () =>
      reportsApi.createSchedule({
        report_type: reportType,
        delivery_channel: channel,
        send_time: sendTime,
        timezone,
        recipients: recipients
          .split(',')
          .map((r) => r.trim())
          .filter(Boolean),
      }),
    onMutate: () => {
      setError(null)
      setNotice(null)
    },
    onSuccess: () => {
      setRecipients('')
      queryClient.invalidateQueries({ queryKey: ['report-schedules'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const toggle = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      reportsApi.updateSchedule(id, { is_active: isActive }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-schedules'] }),
    onError: (err) => setError(errorMessage(err)),
  })

  const remove = useMutation({
    mutationFn: (id: string) => reportsApi.deleteSchedule(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-schedules'] }),
    onError: (err) => setError(errorMessage(err)),
  })

  // 💬 dry_run stays TRUE. Real delivery is a separate, explicit act.
  const preview = useMutation({
    mutationFn: () => reportsApi.runDue({ dry_run: true }),
    onMutate: () => {
      setError(null)
      setNotice(null)
    },
    onSuccess: (res) => {
      // Echo dry_run back from the RESPONSE, not from what we asked for — if
      // the server ever ignored the flag, saying "nothing was sent" would be
      // a lie told confidently.
      setNotice(
        res.dry_run
          ? `Dry run complete — ${res.count} schedule(s) would have fired. Nothing was sent.`
          : `⚠️ ${res.count} schedule(s) were DISPATCHED FOR REAL — the server did not honour dry-run.`,
      )
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const openHtml = useMutation({
    mutationFn: (id: string) => reportsApi.html(id),
    onSuccess: (html) => {
      // Rendered into a blank tab rather than injected into this document —
      // server-generated HTML is not something to drop into our own DOM.
      const blob = new Blob([html], { type: 'text/html' })
      window.open(URL.createObjectURL(blob), '_blank', 'noopener,noreferrer')
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (!canManage) {
    return (
      <>
        <div className="topbar"><div className="page-title">Report Schedules</div></div>
        <div className="content"><NoAccess what="report scheduling" /></div>
      </>
    )
  }

  const schedules = schedulesQ.data ?? []
  const dueNow = (dueQ.data ?? []).filter((d) => d.due)

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Report Schedules</div>
          <div className="page-sub">
            {schedules.length} configured
            {dueNow.length > 0 && ` · ${dueNow.length} due now`}
          </div>
        </div>
        <div className="toolbar">
          <button
            type="button"
            className="btn ghost"
            disabled={preview.isPending}
            onClick={() => preview.mutate()}
          >
            {preview.isPending ? 'Checking…' : 'Dry run (sends nothing)'}
          </button>
        </div>
      </div>

      <div className="content">
        {/* Both delivery channels are currently non-functional, for different
            reasons. Say it before someone schedules and waits. */}
        <div className="mode-banner stub" role="status">
          <strong>DELIVERY NOT OPERATIONAL</strong>
          <span>
            WhatsApp: a scheduled report is unsolicited, so it falls outside the 24-hour session
            window and is refused until a Meta-approved template exists (B-P4-07). Email: no mail
            transport is wired (B-P4-08). Schedules can be created and previewed; they will not
            deliver.
          </span>
        </div>

        {error && <div className="error-banner" role="alert">{error}</div>}
        {notice && <div className="conn-banner ok" role="status">{notice}</div>}

        <div className="card" style={{ marginBottom: 16 }}>
          <div className="t2" style={{ marginBottom: 12 }}>Add a schedule</div>
          <div className="form-row">
            <select
              className="input"
              value={reportType}
              onChange={(e) => setReportType(e.target.value as ReportType)}
              aria-label="Report type"
            >
              {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <select
              className="input"
              value={channel}
              onChange={(e) => setChannel(e.target.value as ReportDeliveryChannel)}
              aria-label="Delivery channel"
            >
              <option value="whatsapp">WhatsApp (needs template)</option>
              <option value="email">Email (no transport)</option>
            </select>
            <input
              className="input"
              type="time"
              value={sendTime}
              onChange={(e) => setSendTime(e.target.value)}
              aria-label="Send time"
            />
            <input
              className="input"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              aria-label="Timezone"
            />
            <input
              className="input grow"
              placeholder="Recipients, comma separated"
              value={recipients}
              onChange={(e) => setRecipients(e.target.value)}
            />
            <button
              type="button"
              className="btn"
              disabled={create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? 'Adding…' : 'Add'}
            </button>
          </div>
          <p className="panel-footnote">
            Send time is a local wall clock in the schedule's own timezone, not a UTC instant — it
            stays at that local hour across daylight-saving changes.
          </p>
        </div>

        {schedulesQ.isLoading ? (
          <SkeletonRows rows={4} height={48} />
        ) : schedulesQ.isError ? (
          <ErrorState error={schedulesQ.error} onRetry={() => schedulesQ.refetch()} />
        ) : schedules.length === 0 ? (
          <div className="state-block">
            <p className="state-title">No schedules</p>
            <p className="state-reason">Reports are only generated on demand from the Reports screen.</p>
          </div>
        ) : (
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>Report</th>
                  <th>Channel</th>
                  <th>Local time</th>
                  <th>Recipients</th>
                  <th>State</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {schedules.map((s) => (
                  <tr key={s.id} className={s.is_active ? '' : 'row-archived'}>
                    <td>{s.report_type}</td>
                    <td className="muted-count">{s.delivery_channel}</td>
                    <td className="muted-count">{s.send_time} <span className="muted-count">{s.timezone}</span></td>
                    <td className="muted-count">{s.recipients.length || '—'}</td>
                    <td>
                      <span className={`badge ${s.is_active ? 'qual-converted' : 'qual-lost'}`}>
                        {s.is_active ? 'active' : 'paused'}
                      </span>
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          type="button"
                          className="btn-secondary sm"
                          disabled={openHtml.isPending}
                          onClick={() => openHtml.mutate(s.id)}
                        >
                          Preview
                        </button>
                        <button
                          type="button"
                          className="btn-secondary sm"
                          disabled={toggle.isPending}
                          onClick={() => toggle.mutate({ id: s.id, isActive: !s.is_active })}
                        >
                          {s.is_active ? 'Pause' : 'Resume'}
                        </button>
                        <button
                          type="button"
                          className="btn-secondary sm"
                          disabled={remove.isPending}
                          onClick={() => remove.mutate(s.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="panel-footnote">
              Preview renders print-ready HTML in a new tab. PDF is not available — no rendering
              library is installed (B-P4-03), and the endpoint answers 501 for that format.
            </p>
          </div>
        )}
      </div>
    </>
  )
}
