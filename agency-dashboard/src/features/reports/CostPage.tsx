/**
 * S21 — Cost tracking and multi-currency revenue rollup.
 *
 * Two rules from the backend contract drive this screen:
 *
 * 1. EVERY cost figure is an estimate unless a line item says otherwise.
 *    Phase 2B never ran, so no call has logged real STT seconds, LLM tokens or
 *    telephony minutes — the numbers are modelled from a rate card (B-P4-04).
 *    `all_estimated` is rendered as a banner, not a footnote.
 *
 * 2. On the rollup, read `complete` BEFORE `total`. An incomplete total silently
 *    omits rows the backend could not convert. A short total that looks whole is
 *    worse than one that is obviously partial, so unconvertible rows get their
 *    own section rather than being dropped.
 *
 * The UI never converts currency itself. The backend uses the FX snapshot in
 * effect at each transaction's own timestamp, so a report re-run next week is
 * identical; re-deriving anything here against a live rate would break that.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { usageApi } from '../../lib/api'
import { formatMoney } from '../../lib/money'
import { ErrorState, SkeletonCards, SkeletonRows } from '../../components/DataState'

const PERIODS = ['today', '7d', '30d', '90d', 'mtd'] as const

export default function CostPage() {
  const [period, setPeriod] = useState<string>('30d')

  const [showRates, setShowRates] = useState(false)

  const costQ = useQuery({
    queryKey: ['cost', period],
    queryFn: () => usageApi.cost({ period }),
  })
  // Only fetched when opened — the rate card is reference data, not something
  // every visit needs.
  const rateCardQ = useQuery({
    queryKey: ['rate-card'],
    queryFn: usageApi.rateCard,
    enabled: showRates,
  })
  const rollupQ = useQuery({
    queryKey: ['revenue-rollup', period],
    queryFn: () => usageApi.revenueRollup({ period }),
  })

  const cost = costQ.data
  const rollup = rollupQ.data

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Cost &amp; Revenue</div>
          <div className="page-sub">
            {cost ? `${cost.period.start} → ${cost.period.end}` : 'Loading…'}
          </div>
        </div>
        <div className="toolbar">
          {PERIODS.map((p) => (
            <button
              key={p}
              type="button"
              className={`btn ghost${p === period ? ' active' : ''}`}
              onClick={() => setPeriod(p)}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="content">
        {/* ── Cost ── */}
        {costQ.isLoading ? (
          <SkeletonCards count={3} />
        ) : costQ.isError ? (
          <ErrorState error={costQ.error} onRetry={() => costQ.refetch()} />
        ) : cost ? (
          <>
            {cost.all_estimated && (
              <div className="mode-banner stub" role="status">
                <strong>ALL ESTIMATED</strong>
                <span>
                  No real provider usage has ever been logged, so every figure below is modelled
                  from rate card <code>{cost.rate_card.version}</code> — not metered. {cost.disclaimer}
                </span>
              </div>
            )}

            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-head">
                <div className="t2">Cost breakdown</div>
                <span className="muted-count">basis: {cost.cost_basis}</span>
              </div>

              {cost.line_items.length === 0 ? (
                <p className="state-reason" style={{ margin: 0 }}>
                  No usage recorded in this period.
                </p>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>STT</th>
                      <th>LLM tokens</th>
                      <th>TTS chars</th>
                      <th>Telephony</th>
                      <th>Cost (USD)</th>
                      <th>Basis</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cost.line_items.slice(0, 50).map((li) => (
                      <tr key={li.id}>
                        <td className="muted-count">{new Date(li.at).toLocaleDateString()}</td>
                        <td className="muted-count">
                          {li.stt_seconds != null ? `${li.stt_seconds}s` : '—'}
                        </td>
                        <td className="muted-count">
                          {li.llm_input_tokens != null || li.llm_output_tokens != null
                            ? `${li.llm_input_tokens ?? 0} / ${li.llm_output_tokens ?? 0}`
                            : '—'}
                        </td>
                        <td className="muted-count">{li.tts_characters ?? '—'}</td>
                        <td className="muted-count">
                          {li.telephony_seconds != null ? `${li.telephony_seconds}s` : '—'}
                        </td>
                        <td>
                          {li.cost_usd != null
                            ? formatMoney(li.cost_usd, 'USD', { maximumFractionDigits: 4 })
                            : '—'}
                        </td>
                        <td>
                          {/* Per-line, because a mixed report can carry both. */}
                          <span className={`badge ${li.is_estimated ? 'qual-warm' : 'qual-converted'}`}>
                            {li.is_estimated ? 'estimated' : 'metered'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {cost.line_items.length > 50 && (
                <p className="panel-footnote">
                  Showing the first 50 of {cost.line_items.length} rows. The summary above covers
                  all of them.
                </p>
              )}
              <p className="panel-footnote">{cost.rate_card.provenance}</p>

              <button
                type="button"
                className="btn-secondary sm"
                onClick={() => setShowRates((v) => !v)}
              >
                {showRates ? 'Hide rate card' : 'Show rate card'}
              </button>

              {showRates && (
                <div className="rate-card">
                  {rateCardQ.isLoading ? (
                    <SkeletonRows rows={3} height={30} />
                  ) : rateCardQ.isError ? (
                    <ErrorState error={rateCardQ.error} onRetry={() => rateCardQ.refetch()} />
                  ) : rateCardQ.data ? (
                    <>
                      <p className="panel-footnote">
                        Version <code>{rateCardQ.data.rate_card_version}</code> ·{' '}
                        {rateCardQ.data.formula}
                      </p>
                      <div className="field-list">
                        {Object.entries(rateCardQ.data.rates_usd).map(([k, v]) => (
                          <div key={k} className="field-row">
                            <span className="field-label">{k}</span>
                            <span className="field-value">
                              {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                            </span>
                          </div>
                        ))}
                      </div>
                      {/* The targets these estimates are measured against. */}
                      <div className="t3" style={{ margin: '12px 0 6px' }}>Targets (USD/min)</div>
                      <div className="field-list">
                        {Object.entries(rateCardQ.data.targets_usd_per_min).map(([lang, t]) => (
                          <div key={lang} className="field-row">
                            <span className="field-label">{lang}</span>
                            <span className="field-value">{t.low} – {t.high}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : null}
                </div>
              )}
            </div>
          </>
        ) : null}

        {/* ── Revenue rollup ── */}
        {rollupQ.isLoading ? (
          <SkeletonRows rows={4} height={48} />
        ) : rollupQ.isError ? (
          <ErrorState error={rollupQ.error} onRetry={() => rollupQ.refetch()} />
        ) : rollup ? (
          <div className="card">
            <div className="card-head">
              <div className="t2">Revenue rollup</div>
              <span className="muted-count">
                {rollup.rows_converted} of {rollup.rows_in} rows converted
              </span>
            </div>

            {/* `complete` is checked before `total` is shown, per the contract. */}
            <div className="rollup-total">
              <span className="rollup-amount">
                {formatMoney(rollup.total, rollup.quote_currency)}
              </span>
              {!rollup.complete && (
                <span className="badge qual-hot">PARTIAL</span>
              )}
            </div>

            {rollup.total_is_partial && (
              <div className="state-block state-error" style={{ marginTop: 12 }}>
                <p className="state-title">This total is incomplete</p>
                <p className="state-reason">
                  {rollup.total_note} {rollup.rows_unconvertible} row
                  {rollup.rows_unconvertible === 1 ? '' : 's'} could not be converted and are
                  excluded — they were not counted as zero. {rollup.unconvertible.remedy}
                </p>
              </div>
            )}

            {rollup.by_currency.length > 0 && (
              <table className="table" style={{ marginTop: 12 }}>
                <thead>
                  <tr>
                    <th>Currency</th>
                    <th>Rows</th>
                    <th>Native</th>
                    <th>Converted</th>
                  </tr>
                </thead>
                <tbody>
                  {rollup.by_currency.map((b) => (
                    <tr key={b.currency}>
                      <td>{b.currency}</td>
                      <td className="muted-count">{b.rows}</td>
                      <td>{formatMoney(b.native_amount, b.currency)}</td>
                      <td>{formatMoney(b.converted_inr, rollup.quote_currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {/* Shown explicitly. Dropping these would make the total look whole. */}
            {rollup.unconvertible.rows > 0 && (
              <>
                <div className="t3" style={{ margin: '16px 0 8px' }}>Excluded from the total</div>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Currency</th>
                      <th>Rows</th>
                      <th>Native</th>
                      <th>Why</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rollup.unconvertible.by_currency.map((b) => (
                      <tr key={b.currency}>
                        <td>{b.currency}</td>
                        <td className="muted-count">{b.rows}</td>
                        <td>{formatMoney(b.native_amount, b.currency)}</td>
                        <td className="muted-count">{b.reasons.join('; ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}

            <p className="panel-footnote">
              {rollup.conversion_basis} Converted using the FX snapshot in effect at each
              transaction's own timestamp, so re-running this later gives the same answer.
            </p>
          </div>
        ) : null}
      </div>
    </>
  )
}
