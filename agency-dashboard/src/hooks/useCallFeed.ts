/**
 * `useCallFeed` — subscribe a component to the live feed for one call.
 *
 * Subscribes on mount, unsubscribes on unmount, groups incoming frames by type,
 * and exposes connection status so a screen can show the "reconnecting — data
 * may be stale" banner the contract requires. Losing frames during a gap is
 * acceptable; presenting stale data as current is not, which is why `isStale`
 * is part of the public return rather than something callers derive.
 *
 * StrictMode: React 19 double-invokes effects in dev. Connections are pooled
 * and ref-counted in `lib/ws.ts` (`acquireCallFeed`), so the mount/unmount/mount
 * cycle re-uses ONE socket instead of opening two. See the registry comment
 * there for the mechanism.
 */
import { useCallback, useEffect, useMemo, useReducer, useState } from 'react'

import { acquireCallFeed } from '../lib/ws'
import type { CallFeedAuthMode, CallFeedError, CallFeedStatus, CallFeedStatusEvent } from '../lib/ws'
import { UNKNOWN_MESSAGE_TYPE } from '../types/ws'
import type {
  CallFeedMessage,
  CallStatusMessage,
  SentimentMessage,
  SuggestionMessage,
  TakeoverStateMessage,
  TranscriptMessage,
  UnknownMessage,
  WhisperMessage,
} from '../types/ws'

/* ────────────────────────────────────────────────────────────────────── */

export interface CallFeedCaps {
  transcripts: number
  sentiments: number
  suggestions: number
  unknown: number
}

/**
 * A long call produces an unbounded transcript stream. Caps keep the arrays
 * (and the React commit cost) bounded; the oldest entries drop first.
 */
export const DEFAULT_CALL_FEED_CAPS: CallFeedCaps = {
  transcripts: 500,
  sentiments: 300,
  suggestions: 100,
  unknown: 50,
}

export interface CallFeedData {
  transcripts: TranscriptMessage[]
  sentiments: SentimentMessage[]
  suggestions: SuggestionMessage[]
  /** Documented-but-never-emitted variant. Expect this to stay empty. */
  whispers: WhisperMessage[]
  /** Latest lifecycle frame — `null` until the backend sends one. */
  callStatus: CallStatusMessage | null
  /**
   * Latest takeover broadcast. This — not local optimistic state — is the
   * source of truth for takeover UI: an operator who believes they hold a live
   * call but does not will talk over an AI that is still speaking.
   */
  takeover: TakeoverStateMessage | null
  /** Unrecognised frames, retained only for debugging. Never render these. */
  unknown: UnknownMessage[]
  /** Total frames received, including ignored ones. */
  messageCount: number
  lastMessageAt: number | null
}

const EMPTY_DATA: CallFeedData = {
  transcripts: [],
  sentiments: [],
  suggestions: [],
  whispers: [],
  callStatus: null,
  takeover: null,
  unknown: [],
  messageCount: 0,
  lastMessageAt: null,
}

type CallFeedAction =
  | { kind: 'message'; message: CallFeedMessage; caps: CallFeedCaps; at: number }
  | { kind: 'reset' }

/** Append with a cap, dropping oldest. Returns a new array — never mutates. */
function appendCapped<T>(list: T[], item: T, cap: number): T[] {
  if (cap <= 0) return list
  const next = list.length >= cap ? list.slice(list.length - cap + 1) : list.slice()
  next.push(item)
  return next
}

function reducer(state: CallFeedData, action: CallFeedAction): CallFeedData {
  if (action.kind === 'reset') return EMPTY_DATA

  const { message, caps, at } = action
  const base: CallFeedData = {
    ...state,
    messageCount: state.messageCount + 1,
    lastMessageAt: at,
  }

  switch (message.type) {
    case 'transcript':
      return { ...base, transcripts: appendCapped(state.transcripts, message, caps.transcripts) }
    case 'sentiment':
      return { ...base, sentiments: appendCapped(state.sentiments, message, caps.sentiments) }
    case 'suggestion':
      return { ...base, suggestions: appendCapped(state.suggestions, message, caps.suggestions) }
    case 'whisper':
      return { ...base, whispers: appendCapped(state.whispers, message, caps.suggestions) }
    case 'call_status':
      return { ...base, callStatus: message }
    case 'takeover_state':
      return { ...base, takeover: message }
    case UNKNOWN_MESSAGE_TYPE:
      // Contract: unknown types are ignored, never fatal. Kept only for logs.
      return { ...base, unknown: appendCapped(state.unknown, message, caps.unknown) }
    default:
      // Unreachable while the union is exhaustive; still returns state rather
      // than throwing, because a runtime frame is not bound by our types.
      return base
  }
}

/* ────────────────────────────────────────────────────────────────────── */

export interface UseCallFeedOptions {
  /** Set false to hold off connecting (e.g. before a call id is known). */
  enabled?: boolean
  caps?: Partial<CallFeedCaps>
  /** Defaults to the stored access token. */
  token?: string | null
  /** Full URL override, mainly for tests. */
  url?: string
  baseUrl?: string
  authMode?: CallFeedAuthMode
}

export interface UseCallFeedResult extends CallFeedData {
  status: CallFeedStatus
  /**
   * `true` whenever the socket is not open. Drive the "reconnecting — data may
   * be stale" banner from this; do not infer freshness from message arrival.
   */
  isStale: boolean
  isConnected: boolean
  /** Consecutive failed connection attempts; 0 while open. */
  reconnectAttempt: number
  error: CallFeedError | null
  /** False until a socket has opened once — separates "never worked" from "dropped". */
  hasEverConnected: boolean
  /** Clear the accumulated buffers without touching the connection. */
  reset: () => void
}

const CLOSED_EVENT: CallFeedStatusEvent = {
  status: 'closed',
  attempt: 0,
  error: null,
  hasEverOpened: false,
}

export function useCallFeed(
  callId: string | null | undefined,
  options: UseCallFeedOptions = {},
): UseCallFeedResult {
  const { enabled = true, token, url, baseUrl, authMode } = options

  const [data, dispatch] = useReducer(reducer, EMPTY_DATA)
  const [statusEvent, setStatusEvent] = useState<CallFeedStatusEvent>(CLOSED_EVENT)

  const capTranscripts = options.caps?.transcripts ?? DEFAULT_CALL_FEED_CAPS.transcripts
  const capSentiments = options.caps?.sentiments ?? DEFAULT_CALL_FEED_CAPS.sentiments
  const capSuggestions = options.caps?.suggestions ?? DEFAULT_CALL_FEED_CAPS.suggestions
  const capUnknown = options.caps?.unknown ?? DEFAULT_CALL_FEED_CAPS.unknown

  const caps = useMemo<CallFeedCaps>(
    () => ({
      transcripts: capTranscripts,
      sentiments: capSentiments,
      suggestions: capSuggestions,
      unknown: capUnknown,
    }),
    [capTranscripts, capSentiments, capSuggestions, capUnknown],
  )

  const reset = useCallback(() => {
    dispatch({ kind: 'reset' })
  }, [])

  // Clear buffers when the call changes. Declared BEFORE the subscribe effect so
  // it runs first in the same commit; `reset` is idempotent, so StrictMode's
  // double-invoke is harmless.
  useEffect(() => {
    dispatch({ kind: 'reset' })
  }, [callId])

  useEffect(() => {
    // No direct setState here: when disabled we derive the closed status at
    // render time instead (see `effectiveStatus` below), which avoids the
    // cascading render a synchronous setState in an effect body would cause.
    if (!enabled || !callId) return

    // Pooled + ref-counted: StrictMode's mount/unmount/mount lands inside the
    // release grace window and re-uses this same socket.
    const lease = acquireCallFeed(callId, { token, url, baseUrl, authMode })

    // `onStatusChange` fires synchronously with the current snapshot on
    // subscribe, so this both seeds and subscribes in one call.
    const offStatus = lease.feed.onStatusChange(setStatusEvent)
    const offMessage = lease.feed.onMessage((message) => {
      dispatch({ kind: 'message', message, caps, at: Date.now() })
    })

    return () => {
      offStatus()
      offMessage()
      // Releases the ref; the socket itself is closed only when the last
      // consumer has gone and the grace period elapses. Any pending reconnect
      // timer is cleared inside `close()`, so nothing can fire post-unmount.
      lease.release()
    }
  }, [callId, enabled, token, url, baseUrl, authMode, caps])

  // Derived rather than stored: while disabled (or before a call id exists)
  // the feed is definitionally closed, and any status left over from a previous
  // enabled run would be stale.
  const effective = enabled && callId ? statusEvent : CLOSED_EVENT

  return {
    ...data,
    status: effective.status,
    isStale: effective.status !== 'open',
    isConnected: effective.status === 'open',
    reconnectAttempt: effective.attempt,
    error: effective.error,
    hasEverConnected: effective.hasEverOpened,
    reset,
  }
}

export default useCallFeed
