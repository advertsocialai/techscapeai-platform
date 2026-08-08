/**
 * S20 — Daily / weekly / monthly reports.
 *
 * The backend goes to real trouble to tell us when a figure is not a
 * measurement: `warnings[]`, `data_quality.ai_stub_mode`,
 * `data_quality.not_trustworthy[]`, and on the sentiment block both
 * `stub_derived` and `is_constant`. All of that exists because, with no
 * Anthropic API key, every completed call writes the SAME lead_score (40) and
 * sentiment (0.4) — so a sentiment "trend" is a flat line by construction, not
 * an observation about customers.
 *
 * A dashboard that renders that number without its caveat is actively
 * misleading, which is why the warnings render ABOVE the figures rather than in
 * a footnote nobody reads. See B-P4-05 and DEBT-07.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { reportsApi } from '../../lib/api'
import { formatMoney } from '../../lib/money'
import { ErrorState, SkeletonCards, SkeletonRows } from '../../components/DataState'
import type { ReportType } from '../../types/travel'

const TABS: ReportType[] = ['daily', 'weekly', 'monthly']

function Metric({ label, value, note }: { label: string; value: React.ReactNode; note?: string }) {
  return (
    <div className="stat">
      <div className="t4" style={{ marginBottom: 8 }}>{label}</div>
      <div className="stat-val">{value}</div>
      {note && <div className="stat-label">{note}</div>}
    </div>
  )
}

export default function ReportsPage() {
  const [type, setType] = useState<ReportType>('daily')

  const reportQ = useQuery({
    queryKey: ['report', type],
    queryFn: () =>
      type === 'daily'
        ? reportsApi.daily()
        : type === 'weekly'
          ? reportsApi.weekly()
          : reportsApi.monthly(),
  })

  const report = reportQ.data

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Reports</div>
          <div className="page-sub">
            {report
              ? `${report.period.start} → ${report.period.end} (${report.period.days}d)`
              : 'Loading…'}
          </div>
        </div>
        <div className="toolbar">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              className={`btn ghost${t === type ? ' active' : ''}`}
              onClick={() => setType(t)}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="content">
        {reportQ.isLoading ? (
          <>
            <SkeletonCards count={4} />
            <div style={{ height: 16 }} />
            <SkeletonRows rows={3} height={60} />
          </>
        ) : reportQ.isError ? (
          <ErrorState error={reportQ.error} onRetry={() => reportQ.refetch()} />
        ) : !report ? null : (
          <>
            {/* Caveats FIRST. A figure whose caveat is below the fold is a
                figure that will be quoted without it. */}
            {report.data_quality.ai_stub_mode && (
              <div className="mode-banner stub" role="status">
                <strong>AI STUB MODE</strong>
                <span>
                  {report.data_quality.ai_stub_reason ??
                    'No AI key configured — scores below are constants written by the stub pipeline, not measurements.'}
                </span>
              </div>
            )}

            {report.warnings.length > 0 && (
              <div className="warning-list" role="status">
                {report.warnings.map((w, i) => (
                  <p key={i} className="warning-item">{w}</p>
                ))}
              </div>
            )}

            <div className="grid-4" style={{ marginBottom: 16 }}>
              <Metric
                label="Calls"
                value={report.calls.total}
                note={`${report.calls.completed} completed · ${report.calls.connected_rate_pct}% connected`}
              />
              <Metric
                label="Leads"
                value={report.funnel.leads_total}
                note={`${report.funnel.hot_leads} hot · ${report.funnel.conversion_rate_pct}% converted`}
              />
              <Metric
                label="Booked"
                value={report.funnel.booked}
                note={`${report.funnel.lost} lost`}
              />
              <Metric
                label="Avg call"
                value={`${Math.round(report.calls.avg_duration_sec)}s`}
                note={`over ${report.calls.calls_with_duration} calls`}
              />
            </div>

            <div className="grid-2">
              <div className="card">
                <div className="t2" style={{ marginBottom: 12 }}>Revenue</div>
                {!report.revenue.available ? (
                  <p className="state-reason" style={{ margin: 0 }}>
                    {report.revenue.reason ?? 'No revenue data for this period.'}
                  </p>
                ) : (
                  <>
                    <div className="field-list">
                      {Object.entries(report.revenue.collected_by_currency).map(([cur, amt]) => (
                        <div key={cur} className="field-row">
                          <span className="field-label">{cur}</span>
                          <span className="field-value">{formatMoney(amt, cur)}</span>
                        </div>
                      ))}
                    </div>
                    {report.revenue.note && (
                      <p className="panel-footnote">{report.revenue.note}</p>
                    )}
                  </>
                )}
              </div>

              <div className="card">
                <div className="t2" style={{ marginBottom: 12 }}>Sentiment</div>
                {/* The two fields that decide whether this panel means anything. */}
                {report.sentiment.stub_derived || report.sentiment.is_constant ? (
                  <div className="state-block state-error">
                    <p className="state-title">Not a measurement</p>
                    <p className="state-reason">
                      {report.sentiment.is_constant
                        ? `All ${report.sentiment.samples} samples carry the same value — this is the stub pipeline's constant, not customer sentiment.`
                        : 'These scores were produced by the stub pipeline rather than a model.'}
                      {' '}Any trend shown would be an artefact. Add an Anthropic API key to get
                      real scores.
                    </p>
                  </div>
                ) : (
                  <div className="field-list">
                    <div className="field-row">
                      <span className="field-label">Average</span>
                      <span className="field-value">
                        {report.sentiment.avg_score_raw?.toFixed(3) ?? '—'}
                      </span>
                    </div>
                    <div className="field-row">
                      <span className="field-label">Trend</span>
                      <span className="field-value">
                        {report.sentiment.trend
                          ? `${report.sentiment.trend.direction} (${report.sentiment.trend.delta.toFixed(3)})`
                          : 'not enough samples'}
                      </span>
                    </div>
                    <div className="field-row">
                      <span className="field-label">Samples</span>
                      <span className="field-value">{report.sentiment.samples}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {report.top_packages.length > 0 && (
              <div className="card" style={{ marginTop: 16 }}>
                <div className="t2" style={{ marginBottom: 12 }}>Top packages</div>
                <ul className="rule-list">
                  {report.top_packages.map((p) => (
                    <li key={p.package_id} className="rule-item">
                      <span>{p.name ?? p.package_id}</span>
                      <span className="muted-count">{p.leads_matched} leads · {p.paid_links} paid</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Which figures the backend itself says not to trust. */}
            {report.data_quality.not_trustworthy.length > 0 && (
              <div className="card" style={{ marginTop: 16 }}>
                <div className="t2" style={{ marginBottom: 10 }}>Do not rely on</div>
                <ul className="unavailable-list">
                  {report.data_quality.not_trustworthy.map((f, i) => <li key={i}>{f}</li>)}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}
