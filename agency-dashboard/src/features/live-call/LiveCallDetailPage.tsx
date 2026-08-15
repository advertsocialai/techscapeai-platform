/**
 * S11 — live transcript, sentiment, suggestions and takeover for ONE call.
 *
 * Two data sources, deliberately kept distinct:
 *   - REST `callsApi.transcript` seeds the history that happened BEFORE this
 *     screen opened. Fetched once.
 *   - The WS feed carries everything from now on.
 *
 * They are concatenated, not merged-and-deduplicated. `seq` is genuinely
 * monotonic per call now (both emit sites derive it from the real transcript
 * count via `_next_seq()` — the old hardcoded `seq: 1` is fixed), but frames
 * recorded before that fix still carry the old value, so identity-based dedupe
 * against history remains unsafe. The seam is therefore drawn by TIME — WS
 * lines older than the seed's newest are dropped — and the small overlap risk
 * is accepted rather than papered over with a fake identity.
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { callsApi } from '../../lib/api'
import { useCallFeed } from '../../hooks/useCallFeed'
import { ErrorState, SkeletonRows } from '../../components/DataState'
import type { TranscriptMessage } from '../../types/ws'
import TakeoverControls from './TakeoverControls'
import CallEventsPanel from './CallEventsPanel'
import {
  ConnectionBanner,
  SentimentPanel,
  SuggestionsPanel,
  TranscriptStream,
  UnavailablePanels,
} from './LivePanels'

export default function LiveCallDetailPage() {
  const { callId } = useParams<{ callId: string }>()

  // The live list is the only route that returns call rows; there is no
  // GET /calls/{id}. Pull the row out of it rather than inventing an endpoint.
  const callsQ = useQuery({
    queryKey: ['calls', 'live'],
    queryFn: callsApi.live,
    refetchInterval: 10000,
  })
  const call = callsQ.data?.find((c) => c.id === callId) ?? null

  const seedQ = useQuery({
    queryKey: ['calls', callId, 'transcript'],
    queryFn: () => callsApi.transcript(callId!),
    enabled: !!callId,
    // The WS feed owns everything after mount; refetching would fight it.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })

  const feed = useCallFeed(callId, { enabled: !!callId })

  const seedLines = useMemo<TranscriptMessage[]>(
    () =>
      (seedQ.data ?? []).map((row) => ({
        type: 'transcript' as const,
        call_id: row.call_id,
        speaker: row.speaker as TranscriptMessage['speaker'],
        text_original: row.text_original,
        text_translated: row.text_translated,
        language: call?.language ?? 'en',
        timestamp_ms: row.timestamp_ms,
        is_final: true,
      })),
    [seedQ.data, call?.language],
  )

  const lines = useMemo(() => {
    if (seedLines.length === 0) return feed.transcripts
    const newestSeed = Math.max(...seedLines.map((l) => l.timestamp_ms))
    // Drop WS frames that predate the seed rather than showing them twice.
    const live = feed.transcripts.filter((l) => l.timestamp_ms > newestSeed)
    return [...seedLines, ...live]
  }, [seedLines, feed.transcripts])

  if (!callId) return <ErrorState error={new Error('No call id in the URL')} />

  const callIsActive = call?.status === 'active'
  const lifecycle = feed.callStatus?.status ?? call?.status ?? null

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">
            <Link to="/live-call" className="crumb">Live Calls</Link>
            <span className="crumb-sep">/</span>
            {call?.provider_sid ?? callId.slice(0, 8)}
          </div>
          <div className="page-sub">
            {lifecycle ? `status: ${lifecycle}` : 'status unknown'}
            {call && ` · mode: ${call.mode} · ${call.language}`}
          </div>
        </div>
      </div>

      <div className="content">
        <ConnectionBanner
          status={feed.status}
          attempt={feed.reconnectAttempt}
          error={feed.error}
          hasEverConnected={feed.hasEverConnected}
        />

        {/* A completed call is not an error, but the takeover controls and the
            "waiting for more" framing would both be wrong for it. */}
        {lifecycle === 'completed' && (
          <div className="conn-banner info" role="status">
            <span>This call has ended. The transcript below is final.</span>
          </div>
        )}

        <div className="live-detail-grid">
          <div className="live-detail-main">
            {seedQ.isLoading ? (
              <SkeletonRows rows={6} height={54} />
            ) : seedQ.isError ? (
              <ErrorState error={seedQ.error} onRetry={() => seedQ.refetch()} />
            ) : (
              <TranscriptStream lines={lines} isStale={feed.isStale} />
            )}
          </div>

          <aside className="live-detail-side">
            <TakeoverControls
              callId={callId}
              confirmed={feed.takeover?.takeover_state ?? null}
              isStale={feed.isStale}
              callIsActive={callIsActive}
            />
            <SentimentPanel sentiments={feed.sentiments} />
            <SuggestionsPanel suggestions={feed.suggestions} />
            <CallEventsPanel callId={callId} />
            <UnavailablePanels />
          </aside>
        </div>
      </div>
    </>
  )
}
