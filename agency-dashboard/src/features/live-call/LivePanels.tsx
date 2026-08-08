/**
 * S11 panels: connection banner, transcript stream, sentiment, suggestions.
 *
 * Each renders ONLY what the backend actually emits. Where the product spec
 * asks for something with no publisher, this file says so on screen instead of
 * rendering an empty box the operator would read as "nothing happening".
 */
import { useEffect, useRef } from 'react'

import type {
  SentimentMessage,
  SuggestionMessage,
  TranscriptMessage,
} from '../../types/ws'
import type { CallFeedStatus } from '../../lib/ws'

/* ── Connection status ──────────────────────────────────────────────────── */

const STATUS_TEXT: Record<CallFeedStatus, string> = {
  connecting: 'Connecting to the live feed…',
  open: 'Live',
  reconnecting: 'Reconnecting — data below may be stale',
  closed: 'Live feed closed',
}

export function ConnectionBanner({
  status,
  attempt,
  error,
  hasEverConnected,
}: {
  status: CallFeedStatus
  attempt: number
  error: { message: string } | null
  hasEverConnected: boolean
}) {
  const tone = status === 'open' ? 'ok' : status === 'connecting' ? 'info' : 'warn'

  return (
    <div className={`conn-banner ${tone}`} role="status">
      <span className={`conn-dot ${tone}`} aria-hidden="true" />
      <span>{STATUS_TEXT[status]}</span>
      {attempt > 0 && <span className="conn-detail">attempt {attempt}</span>}
      {/* "Never connected" and "dropped" need different responses from the
          operator, so they must not look the same. */}
      {!hasEverConnected && status !== 'connecting' && status !== 'open' && (
        <span className="conn-detail">never connected — check auth or the WS URL</span>
      )}
      {error && <span className="conn-detail">{error.message}</span>}
    </div>
  )
}

/* ── Transcript ─────────────────────────────────────────────────────────── */

function speakerLabel(speaker: string): string {
  if (speaker === 'customer') return 'Customer'
  if (speaker === 'ai') return 'AI'
  if (speaker === 'agent') return 'Agent'
  return speaker
}

export function TranscriptStream({
  lines,
  isStale,
}: {
  lines: TranscriptMessage[]
  isStale: boolean
}) {
  const endRef = useRef<HTMLDivElement | null>(null)
  const scrollerRef = useRef<HTMLDivElement | null>(null)
  const pinnedRef = useRef(true)

  // Auto-scroll ONLY while the operator is already at the bottom. Yanking the
  // view back down while they are reading earlier turns is worse than not
  // scrolling at all.
  useEffect(() => {
    const el = scrollerRef.current
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    pinnedRef.current = distance < 80
  })

  useEffect(() => {
    if (pinnedRef.current) endRef.current?.scrollIntoView({ block: 'end' })
  }, [lines.length])

  return (
    <div className="card transcript-card">
      <div className="t2" style={{ marginBottom: 10 }}>
        Transcript
        <span className="muted-count"> · {lines.length} turns</span>
      </div>

      <div className="transcript-scroll" ref={scrollerRef}>
        {lines.length === 0 ? (
          <div className="state-block">
            <p className="state-title">No transcript yet</p>
            <p className="state-reason">
              {isStale
                ? 'The live feed is not connected, so nothing can arrive right now.'
                : 'Connected and waiting. Lines appear as the backend finalises each utterance.'}
            </p>
          </div>
        ) : (
          lines.map((line, i) => (
            <div
              key={`${line.timestamp_ms}-${i}`}
              className={`transcript-line speaker-${line.speaker}`}
            >
              <div className="transcript-meta">
                <span className="transcript-speaker">{speakerLabel(line.speaker)}</span>
                <span className="transcript-lang">{line.language}</span>
              </div>
              <p className="transcript-text">{line.text_original}</p>
              {/* Only shown when the backend actually translated. Rendering an
                  empty translation slot implies a failure that did not happen. */}
              {line.text_translated && line.text_translated !== line.text_original && (
                <p className="transcript-translated">{line.text_translated}</p>
              )}
            </div>
          ))
        )}
        <div ref={endRef} />
      </div>
    </div>
  )
}

/* ── Sentiment ──────────────────────────────────────────────────────────── */

const DIMENSIONS = [
  { key: 'excitement', label: 'Excitement' },
  { key: 'intent', label: 'Buying intent' },
  { key: 'price_sensitivity', label: 'Price sensitivity' },
] as const

export function SentimentPanel({ sentiments }: { sentiments: SentimentMessage[] }) {
  const latest = sentiments[sentiments.length - 1] ?? null

  return (
    <div className="card">
      <div className="t2" style={{ marginBottom: 10 }}>Sentiment</div>

      {!latest ? (
        <div className="state-block">
          <p className="state-title">No sentiment yet</p>
          <p className="state-reason">
            Scored per customer utterance, after the transcript row is written. AI turns are not
            scored.
          </p>
        </div>
      ) : (
        <div className="sentiment-rows">
          {DIMENSIONS.map((d) => {
            const value = latest.scores[d.key]
            const pct = Math.round(value * 100)
            return (
              <div key={d.key} className="sentiment-row">
                <div className="sentiment-label">
                  <span>{d.label}</span>
                  <span className="sentiment-value">{pct}%</span>
                </div>
                <div className="sentiment-track">
                  <div className="sentiment-fill" style={{ width: `${pct}%` }} />
                </div>
              </div>
            )
          })}
          <p className="panel-footnote">
            Keyword-based scoring. {sentiments.length} update
            {sentiments.length === 1 ? '' : 's'} this session.
          </p>
        </div>
      )}
    </div>
  )
}

/* ── Suggestions ────────────────────────────────────────────────────────── */

export function SuggestionsPanel({ suggestions }: { suggestions: SuggestionMessage[] }) {
  const recent = [...suggestions].reverse().slice(0, 8)

  return (
    <div className="card">
      <div className="t2" style={{ marginBottom: 10 }}>AI suggestions</div>

      {recent.length === 0 ? (
        <div className="state-block">
          <p className="state-title">No suggestions yet</p>
          <p className="state-reason">
            Generated per customer turn. Without an Anthropic API key the backend falls back to
            keyword mode, which produces fewer and blunter prompts.
          </p>
        </div>
      ) : (
        <ul className="suggestion-list">
          {recent.map((s, i) => (
            <li key={i} className="suggestion-item">
              <p className="suggestion-text">{s.text}</p>
              {/* The mode is not decoration: 'keyword' means no LLM was
                  involved, and the operator should weigh it accordingly. */}
              <span className={`badge mode-${s.mode}`}>{s.mode}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/* ── The gap, stated on screen ──────────────────────────────────────────── */

/**
 * The Phase 2 spec asks for live speaking indicators, per-turn intent, a call
 * event stream and structured extraction. NO backend publisher emits any of
 * them (see `DEBT-15`). Rendering empty panels for them would read as "the call
 * is quiet"; this says what is actually true.
 */
export function UnavailablePanels() {
  return (
    <div className="card">
      <div className="t2" style={{ marginBottom: 10 }}>Not available yet</div>
      <p className="state-reason" style={{ marginBottom: 10 }}>
        These are in the screen spec but have no backend publisher, so there is nothing to show.
        Tracked as <strong>DEBT-15</strong> — a backend gap, not a display problem.
      </p>
      <ul className="unavailable-list">
        <li><strong>Speaking indicator</strong> — no <code>speaking</code> frames are emitted</li>
        <li><strong>Live intent</strong> — no <code>intent</code> frames are emitted</li>
        <li><strong>Call event stream</strong> — no <code>event</code> frames are emitted</li>
        <li><strong>Structured extraction</strong> — no <code>extraction</code> frames are emitted</li>
      </ul>
    </div>
  )
}
