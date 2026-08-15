import type { TakeoverState } from './travel'

export type { TakeoverState }

/**
 * WebSocket message contract for `ws://<host>/ws/calls/{call_id}`.
 *
 * SOURCE OF TRUTH: the backend CODE, not the spec doc. Every interface below
 * was read off the actual `call_feed.publish(...)` call sites in
 * `api/app/`. Where `.claude/skills/gogaga-backend/references/api-conventions.md`
 * disagrees, the disagreement is recorded inline rather than papered over —
 * the doc's own recon rule says "MATCH THE EXISTING CODE".
 *
 * Verified publish sites (Phase 5):
 *   routers/travel/webhooks_voice.py:238  -> call_status  (status "active")
 *   routers/travel/webhooks_voice.py:267  -> call_status  (status "completed")
 *   routers/travel/webhooks_voice.py:290  -> transcript
 *   services/travel/sentiment_service.py:127  -> sentiment
 *   services/travel/suggestion_service.py:133 -> suggestion
 *   routers/travel/takeover.py:63             -> takeover_state
 *
 * That is the COMPLETE set. There are no other publish call sites.
 */

/* ────────────────────────────────────────────────────────────────────────
 * Field-level value unions
 * ──────────────────────────────────────────────────────────────────────── */

/**
 * `travel_transcripts.speaker`. The publisher copies the DB column through
 * verbatim (`transcript_row["speaker"]`), so this is not runtime-validated —
 * treat it as a hint for narrowing, not a guarantee. The only value the voice
 * webhook currently INSERTs is `"customer"`; `"ai"` / `"agent"` come from the
 * doc and from other writers of the same table.
 */
export type TranscriptSpeaker = 'customer' | 'ai' | 'agent'

/**
 * `call_status.status`.
 *
 * EMITTED BY BACKEND: only `"active"` and `"completed"` — the two literal
 * strings hardcoded at webhooks_voice.py:240 and :269.
 *
 * `"failed"` is listed in api-conventions.md but NO code path emits it. It is
 * kept in the union so a `switch` stays defensive if the backend adds it, but
 * do not build UI that expects to ever see it today.
 */
export type CallLifecycleStatus = 'active' | 'completed' | 'failed'

/**
 * `call_status.mode` — read from `travel_calls.mode` with a default of `"ai"`.
 * `takeover_service.py` writes `mode="ai"` and `mode="agent"`. `"conference"`
 * appears in api-conventions.md but is never written by any code path.
 */
export type CallMode = 'ai' | 'agent' | 'conference'


/**
 * `suggestion.mode` — the ternary at suggestion_service.py:137:
 * `"claude" if settings.ANTHROPIC_API_KEY else "keyword"`. Exactly two values.
 */
export type SuggestionMode = 'claude' | 'keyword'

/**
 * Return value of `sentiment_service.score_text()` (sentiment_service.py:81-87).
 *
 * EXACTLY three dimensions. api-conventions.md documents a fourth, `urgency` —
 * it is NOT computed and NOT emitted, so it is deliberately absent here rather
 * than added as an optional field that a chart would silently render as 0.
 */
export interface SentimentScores {
  excitement: number
  intent: number
  price_sensitivity: number
}

/* ────────────────────────────────────────────────────────────────────────
 * Messages actually emitted by the backend
 * ──────────────────────────────────────────────────────────────────────── */

/** webhooks_voice.py:290 — emitted once per finalised utterance. */
export interface TranscriptMessage {
  type: 'transcript'
  call_id: string
  /**
   * OPTIONAL ON PURPOSE.
   *
   * api-conventions.md says `seq` is "monotonically increasing per call (lets
   * the frontend detect gaps after reconnect)". That is now TRUE (wave-2 fix):
   * both emit sites (customer transcript in webhooks_voice.py and AI reply in
   * voice_turn_service.py) derive seq from the call's real transcript count.
   * Gap-detection against it is now legitimate, though still optional here.
   *
   * Kept optional in the type because older recorded frames may carry the
   * historical hardcoded value. Every frame
   * currently reports seq 1, so any "we missed N messages" logic built on it
   * would fire constantly and lie to the user. Typed optional so consumers are
   * forced to handle its absence and are not tempted to trust it.
   */
  seq?: number
  speaker: TranscriptSpeaker
  text_original: string
  /** `transcript_row.get("text_translated")` — nullable in the DB. */
  text_translated: string | null
  /** `call_row.get("language", "en")`, e.g. "en" | "hi" | "te". Free-form. */
  language: string
  timestamp_ms: number
  /** Always `True` at the emit site — the backend has no partial-transcript path yet. */
  is_final: boolean
}

/** webhooks_voice.py:238 (stream start) and :267 (stream stop). */
export interface CallStatusMessage {
  type: 'call_status'
  call_id: string
  status: CallLifecycleStatus
  mode: CallMode
}

/** sentiment_service.py:127 — fired per scored customer utterance. */
export interface SentimentMessage {
  type: 'sentiment'
  call_id: string
  /** FK into `travel_transcripts`. Present in code; absent from the doc. */
  transcript_id: string
  scores: SentimentScores
  /** The doc claims a `seq` here. The code emits none. Never populated today. */
  seq?: number
}

/**
 * suggestion_service.py:133 — the "whisper to the agent" channel.
 *
 * api-conventions.md was corrected to match this shape (`{type, call_id,
 * text, mode}`, discriminator `suggestion`) — it previously specified a
 * `whisper` frame with `{suggestion, confidence}` that was never emitted.
 */
export interface SuggestionMessage {
  type: 'suggestion'
  call_id: string
  text: string
  /** Which generator produced it — Claude, or the keyword fallback. */
  mode: SuggestionMode
}

/**
 * takeover.py:63 — broadcast on every supervisor takeover transition.
 * Not documented in api-conventions.md; verified in code.
 */
export interface TakeoverStateMessage {
  type: 'takeover_state'
  call_id: string
  takeover_state: TakeoverState
}

/* ────────────────────────────────────────────────────────────────────────
 * Documented-but-unseen
 * ──────────────────────────────────────────────────────────────────────── */

/**
 * NOT EMITTED BY BACKEND as of Phase 5 — and deliberately NOT given interfaces.
 *
 * These four type strings circulate in product specs but appear at zero
 * `call_feed.publish` call sites. Their field shapes are entirely unspecified
 * in code, so writing interfaces for them would mean inventing fields, which is
 * worse than having none: a typed-but-fictional `SpeakingMessage` reads as a
 * live capability to anyone building against it.
 *
 * Runtime consequence: if one of these ever arrives it is classified as
 * `UnknownMessage` and ignored, exactly as the contract requires. Give it a
 * real interface only once a real publisher exists.
 */
export const NEVER_EMITTED_MESSAGE_TYPES = [
  'speaking',
  'intent',
  'event',
  'extraction',
] as const

export type NeverEmittedMessageType = (typeof NEVER_EMITTED_MESSAGE_TYPES)[number]

/* ────────────────────────────────────────────────────────────────────────
 * Unknown fallback
 * ──────────────────────────────────────────────────────────────────────── */

/**
 * Client-synthesised discriminator. Chosen so it can never collide with a
 * backend `type` value, which keeps `CallFeedMessage` exhaustively narrowable
 * (a fallback typed `{ type: string }` would overlap every literal branch and
 * defeat `switch` narrowing entirely).
 */
export const UNKNOWN_MESSAGE_TYPE = '__unknown__'

/**
 * Anything the parser could not classify: an unrecognised `type`, a missing or
 * non-string `type`, a non-object body, or a frame that was not valid JSON.
 *
 * api-conventions.md: "Unknown `type` must be ignored by clients, never crash."
 * Producing this value instead of throwing is how that rule is honoured — the
 * raw frame is preserved for logging, and no consumer is obliged to read it.
 */
export interface UnknownMessage {
  type: typeof UNKNOWN_MESSAGE_TYPE
  /** The `type` field as it arrived, or `null` if absent/not-a-string/unparseable. */
  received_type: string | null
  /** Parsed JSON when parseable, otherwise the raw frame. */
  payload: unknown
}

/* ────────────────────────────────────────────────────────────────────────
 * The union
 * ──────────────────────────────────────────────────────────────────────── */

export type KnownCallFeedMessage =
  | TranscriptMessage
  | CallStatusMessage
  | SentimentMessage
  | SuggestionMessage
  | TakeoverStateMessage

export type CallFeedMessage = KnownCallFeedMessage | UnknownMessage

export type KnownCallFeedMessageType = KnownCallFeedMessage['type']

/** Runtime companion to `KnownCallFeedMessageType` — the five real emitted types. */
export const KNOWN_CALL_FEED_MESSAGE_TYPES = [
  'transcript',
  'call_status',
  'sentiment',
  'suggestion',
  'takeover_state',
] as const

const KNOWN_TYPE_SET: ReadonlySet<string> = new Set<string>(KNOWN_CALL_FEED_MESSAGE_TYPES)

export function isKnownCallFeedMessageType(value: string): value is KnownCallFeedMessageType {
  return KNOWN_TYPE_SET.has(value)
}

export function isUnknownMessage(message: CallFeedMessage): message is UnknownMessage {
  return message.type === UNKNOWN_MESSAGE_TYPE
}
