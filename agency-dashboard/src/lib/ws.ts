/**
 * Live-call WebSocket connection manager for `/ws/calls/{call_id}`.
 *
 * Mounted at the app ROOT with no `/api` prefix (api/app/main.py:82 includes
 * `calls_ws_router` directly on `app`), so this does NOT go through the axios
 * instance's `/api` baseURL and does NOT go through Vite's `/api` dev proxy.
 *
 * Responsibilities:
 *   - resolve the socket URL
 *   - carry auth (see the AUTH section — the browser channel is the subprotocol)
 *   - parse frames into the `CallFeedMessage` union, never throwing
 *   - reconnect with capped exponential backoff + jitter
 *   - expose `connecting | open | reconnecting | closed`
 *   - tear down completely on `close()`, including any pending reconnect timer
 *   - share one socket per call across components (React 19 StrictMode safety)
 */
import {
  UNKNOWN_MESSAGE_TYPE,
  isKnownCallFeedMessageType,
} from '../types/ws'
import type { CallFeedMessage, KnownCallFeedMessage, UnknownMessage } from '../types/ws'

/* ────────────────────────────────────────────────────────────────────────
 * AUTH — READ THIS BEFORE WIRING THE LIVE CALL SCREEN
 *
 * The route ORIGINALLY read:
 *   async def call_feed_ws(websocket, call_id, user: dict = Depends(get_current_user))
 * where get_current_user took its token from an `Authorization` header only.
 *
 * That header-only handshake could never work from a browser: the `WebSocket`
 * constructor exposes no way to set request headers, and there is no
 * fetch-style escape hatch. The reference client the backend was originally
 * built against — .claude/skills/gogaga-verifier/scripts/ws_probe.py — uses
 * `websockets.connect(url, additional_headers=headers)`, a Python-client
 * capability with no browser equivalent. Every dashboard handshake was
 * rejected at the HTTP layer before the socket opened, surfacing as a bare
 * close code 1006 that looks like a network blip and retries forever.
 *
 * THAT IS NOW FIXED SERVER-SIDE. `calls.py` depends on `get_current_user_ws`
 * (api/app/core/deps.py), which accepts three channels, in this order:
 *
 *   - `authMode: 'subprotocol'` (DEFAULT, browser-safe): the token rides the
 *     `Sec-WebSocket-Protocol` header, which the WebSocket constructor CAN set:
 *         new WebSocket(url, ['bearer', token])
 *     Preferred over a query string because query strings are written to access
 *     logs, proxy logs and browser history, where a captured access token
 *     outlives its own expiry as a stolen credential.
 *     RFC 6455 requires the server to echo exactly one offered subprotocol;
 *     the backend echoes `bearer` via `ws_accept_subprotocol()`. If it ever
 *     stops, the browser drops a connection the server believes it accepted —
 *     which is why the backend has a regression test pinning the echo.
 *   - `authMode: 'header'`: `Authorization: Bearer <jwt>`, produced by
 *     `buildHandshakeHeaders()` and handed to `socketFactory`. The default
 *     browser factory has nowhere to put headers and ignores them, so this mode
 *     is for header-capable transports only (Node `ws`, a test double, a proxy
 *     that injects the header). It is what ws_probe.py uses, and it still works.
 *   - `authMode: 'query'` (last resort): appends `?token=<jwt>`. The backend
 *     does read it now, but it leaks the JWT into logs and Referer headers.
 *     Use only where a proxy strips unknown subprotocols.
 * ──────────────────────────────────────────────────────────────────────── */

export type CallFeedAuthMode = 'subprotocol' | 'header' | 'query'

/**
 * The subprotocol name the backend matches on (`_WS_SUBPROTOCOL` in deps.py).
 * The offer is `[WS_AUTH_SUBPROTOCOL, token]` — two entries, the second being
 * the raw JWT.
 */
export const WS_AUTH_SUBPROTOCOL = 'bearer'

/**
 * True since the backend grew `get_current_user_ws`. Kept as an exported flag
 * (rather than deleted) so a screen can still branch on it, and so the history
 * of why it existed stays greppable.
 */
export const BROWSER_HANDSHAKE_AUTH_SUPPORTED = true

export const HANDSHAKE_REJECTED_HINT =
  'The /ws/calls handshake was rejected. Check the access token is present and unexpired, and that ' +
  'the server echoes the "bearer" subprotocol (deps.py -> ws_accept_subprotocol). A browser silently ' +
  'drops any connection whose offered subprotocol the server did not echo back.'

/**
 * The subprotocol offer for a handshake, or `undefined` when this mode/token
 * combination should not send one. Never send a bare `['bearer']`: the backend
 * requires two entries and would fall through to the query param.
 */
export function buildHandshakeProtocols(
  token: string | null,
  authMode: CallFeedAuthMode,
): string[] | undefined {
  if (authMode !== 'subprotocol' || !token) return undefined
  return [WS_AUTH_SUBPROTOCOL, token]
}

export const ACCESS_TOKEN_STORAGE_KEY = 'gogaga_access_token'

/**
 * The header set the backend requires. Kept as a real function (rather than
 * inlined into a transport) so a header-capable client can use this module
 * unchanged, and so the requirement stays greppable.
 */
export function buildHandshakeHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function readStoredToken(): string | null {
  try {
    return localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

/* ────────────────────────────────────────────────────────────────────────
 * URL resolution
 * ──────────────────────────────────────────────────────────────────────── */

/**
 * `VITE_WS_BASE_URL` overrides; otherwise derive from the page origin.
 *
 * NOTE for dev: vite.config.ts proxies only `/api`, and this endpoint is at the
 * root (`/ws/...`), so a same-origin derivation from :5174 will not reach the
 * API on :8000. Set `VITE_WS_BASE_URL=ws://localhost:8000` (or add a `/ws`
 * proxy entry) when running locally.
 */
export function resolveWsBaseUrl(explicit?: string): string {
  if (explicit) return explicit.replace(/\/+$/, '')

  const fromEnv: string | undefined = import.meta.env?.VITE_WS_BASE_URL
  if (fromEnv) return fromEnv.replace(/\/+$/, '')

  if (typeof window === 'undefined' || !window.location?.host) return ''

  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${window.location.host}`
}

export function callFeedUrl(
  callId: string,
  options: { baseUrl?: string; token?: string | null; authMode?: CallFeedAuthMode } = {},
): string {
  const base = resolveWsBaseUrl(options.baseUrl)
  const url = `${base}/ws/calls/${encodeURIComponent(callId)}`

  // Last-resort channel. The backend does read this, but it puts the JWT in
  // access logs and Referer headers — prefer 'subprotocol'.
  if (options.authMode === 'query' && options.token) {
    return `${url}?token=${encodeURIComponent(options.token)}`
  }
  return url
}

/* ────────────────────────────────────────────────────────────────────────
 * Frame parsing — total, never throws
 * ──────────────────────────────────────────────────────────────────────── */

function unknownMessage(receivedType: string | null, payload: unknown): UnknownMessage {
  return { type: UNKNOWN_MESSAGE_TYPE, received_type: receivedType, payload }
}

/**
 * Classify a raw frame. ALWAYS returns a value — malformed JSON, a missing
 * `type`, a non-object body, or an unrecognised `type` all become
 * `UnknownMessage`. The contract requires unknown types be ignored rather than
 * crash the client, and a parser that throws would take the socket's message
 * handler down with it.
 */
export function parseCallFeedMessage(raw: unknown): CallFeedMessage {
  let data: unknown = raw

  if (typeof raw === 'string') {
    try {
      data = JSON.parse(raw)
    } catch {
      return unknownMessage(null, raw)
    }
  }

  if (data === null || typeof data !== 'object' || Array.isArray(data)) {
    return unknownMessage(null, data)
  }

  const candidate = (data as { type?: unknown }).type
  if (typeof candidate !== 'string') return unknownMessage(null, data)
  if (!isKnownCallFeedMessageType(candidate)) return unknownMessage(candidate, data)

  // Field-level shape is trusted from here: the backend is the only publisher
  // and every emit site is a literal dict. Deep validation would add a schema
  // dependency without protecting against anything currently possible.
  return data as KnownCallFeedMessage
}

/* ────────────────────────────────────────────────────────────────────────
 * Backoff
 * ──────────────────────────────────────────────────────────────────────── */

export interface BackoffOptions {
  /** Delay before the first retry. */
  baseDelayMs: number
  /** Multiplier per attempt. */
  factor: number
  /** Hard ceiling — the returned delay is never above this. */
  maxDelayMs: number
  /** Fraction of the delay that is randomised, 0..1. 0.5 => delay in [0.5d, d]. */
  jitter: number
}

export const DEFAULT_BACKOFF: BackoffOptions = {
  baseDelayMs: 500,
  factor: 2,
  maxDelayMs: 30_000,
  jitter: 0.5,
}

/**
 * Capped exponential backoff with proportional ("equal") jitter.
 *
 * `attempt` is 1-based. The undithered delay is
 * `min(base * factor^(attempt-1), maxDelayMs)`; jitter then spreads the actual
 * value across `[d*(1-jitter), d]`, which is what stops a fleet of dashboards
 * from reconnecting in lockstep after a backend restart.
 *
 * Guarantees, both exercised by the verification script:
 *   - monotonic non-decreasing in `attempt` (before jitter)
 *   - never exceeds `maxDelayMs`, and never below 0
 */
export function computeBackoffDelay(
  attempt: number,
  options: Partial<BackoffOptions> = {},
  random: () => number = Math.random,
): number {
  const { baseDelayMs, factor, maxDelayMs, jitter } = { ...DEFAULT_BACKOFF, ...options }

  const safeAttempt = Math.max(1, Math.floor(attempt))
  const uncapped = baseDelayMs * Math.pow(factor, safeAttempt - 1)

  // Math.pow overflows to Infinity for large attempts; Math.min still caps it.
  const capped = Math.min(uncapped, maxDelayMs)

  const spread = Math.min(Math.max(jitter, 0), 1)
  const dithered = capped * (1 - spread) + capped * spread * random()

  return Math.max(0, Math.min(Math.round(dithered), maxDelayMs))
}

/* ────────────────────────────────────────────────────────────────────────
 * Transport abstraction
 * ──────────────────────────────────────────────────────────────────────── */

export interface CloseEventLike {
  code: number
  reason?: string
  wasClean?: boolean
}

export interface MessageEventLike {
  data: unknown
}

/**
 * The slice of `WebSocket` this manager uses.
 *
 * Handlers are `on*` PROPERTIES rather than addEventListener/removeEventListener
 * on purpose: teardown is then provably complete — four assignments to `null`
 * and there is no way a listener survives, and no way we leak a listener by
 * failing to pass the identical function reference to `removeEventListener`.
 */
export interface WebSocketLike {
  readyState: number
  close(code?: number, reason?: string): void
  send(data: string): void
  onopen: ((event: unknown) => void) | null
  onclose: ((event: CloseEventLike) => void) | null
  onerror: ((event: unknown) => void) | null
  onmessage: ((event: MessageEventLike) => void) | null
}

/**
 * `protocols` is the browser-safe auth channel and the one that carries the
 * token by default. `headers` is still passed because a Node/test transport can
 * apply it (and ws_probe.py does) — the browser factory below cannot.
 */
export type SocketFactory = (
  url: string,
  headers: Record<string, string>,
  protocols?: string[],
) => WebSocketLike

const defaultSocketFactory: SocketFactory = (url, _headers, protocols) => {
  // `headers` is intentionally dropped: the browser WebSocket constructor
  // accepts no header option. `protocols` is the channel that does work here —
  // it becomes the Sec-WebSocket-Protocol offer the backend reads.
  return (protocols && protocols.length
    ? new WebSocket(url, protocols)
    : new WebSocket(url)) as unknown as WebSocketLike
}

export type TimerHandle = ReturnType<typeof setTimeout>

/* ────────────────────────────────────────────────────────────────────────
 * Status + errors
 * ──────────────────────────────────────────────────────────────────────── */

export type CallFeedStatus = 'connecting' | 'open' | 'reconnecting' | 'closed'

export type CallFeedErrorKind =
  | 'handshake-rejected'
  | 'closed-by-server'
  | 'transport-error'
  | 'retries-exhausted'

export interface CallFeedError {
  kind: CallFeedErrorKind
  code: number | null
  reason: string
  message: string
}

export interface CallFeedStatusEvent {
  status: CallFeedStatus
  /** Consecutive failed connection attempts; 0 while open. */
  attempt: number
  error: CallFeedError | null
  /** True once a socket has opened at least once — distinguishes "never worked" from "dropped". */
  hasEverOpened: boolean
}

/**
 * Close codes we must NOT retry.
 *  - 1000 normal: the call feed ended; hammering it is pointless.
 *  - 1008 policy violation.
 *  - 4404: calls.py:65 closes with this when the call is missing OR out of the
 *    caller's RBAC scope (deliberately indistinguishable). Retrying cannot help
 *    and would be a slow poll against an authorisation failure.
 */
const NON_RETRYABLE_CLOSE_CODES: ReadonlySet<number> = new Set([1000, 1008, 4401, 4403, 4404])

export interface CallFeedSocketOptions {
  /** Full override; otherwise built from `baseUrl` + callId. */
  url?: string
  baseUrl?: string
  /** Defaults to the stored access token. */
  token?: string | null
  authMode?: CallFeedAuthMode
  backoff?: Partial<BackoffOptions>
  socketFactory?: SocketFactory
  random?: () => number
  setTimeoutFn?: (fn: () => void, ms: number) => TimerHandle
  clearTimeoutFn?: (handle: TimerHandle) => void
  /** Give up after this many consecutive failures. Default: unlimited. */
  maxReconnectAttempts?: number
  /**
   * Give up after this many failures when NO connection has ever opened.
   * Guards the browser-auth case: a rejected handshake surfaces as an ordinary
   * 1006, which would otherwise look retryable forever.
   */
  maxHandshakeAttempts?: number
  onMessage?: (message: CallFeedMessage) => void
  onStatusChange?: (event: CallFeedStatusEvent) => void
}

export interface CallFeedSocket {
  connect(): void
  /** Full teardown. Idempotent, and permanent — a closed socket never reconnects. */
  close(): void
  getStatus(): CallFeedStatus
  getStatusEvent(): CallFeedStatusEvent
  onMessage(listener: (message: CallFeedMessage) => void): () => void
  onStatusChange(listener: (event: CallFeedStatusEvent) => void): () => void
  readonly callId: string
}

export function createCallFeedSocket(
  callId: string,
  options: CallFeedSocketOptions = {},
): CallFeedSocket {
  const {
    authMode = 'subprotocol',
    socketFactory = defaultSocketFactory,
    random = Math.random,
    setTimeoutFn = ((fn, ms) => setTimeout(fn, ms)) as (fn: () => void, ms: number) => TimerHandle,
    clearTimeoutFn = ((handle) => clearTimeout(handle)) as (handle: TimerHandle) => void,
    maxReconnectAttempts = Number.POSITIVE_INFINITY,
    maxHandshakeAttempts = 5,
  } = options

  let socket: WebSocketLike | null = null
  let timer: TimerHandle | null = null
  let status: CallFeedStatus = 'closed'
  let attempt = 0
  let hasEverOpened = false
  let lastError: CallFeedError | null = null
  /** Permanent tombstone. Every async continuation checks it. */
  let disposed = false

  const messageListeners = new Set<(message: CallFeedMessage) => void>()
  const statusListeners = new Set<(event: CallFeedStatusEvent) => void>()

  if (options.onMessage) messageListeners.add(options.onMessage)
  if (options.onStatusChange) statusListeners.add(options.onStatusChange)

  /**
   * Cached so repeat reads are referentially stable: `useState`/`useSyncExternal
   * Store` consumers bail out of re-rendering when the object identity is
   * unchanged. Rebuilt only by `refreshSnapshot()`, after all mutations settle.
   */
  let currentEvent: CallFeedStatusEvent = {
    status: 'closed',
    attempt: 0,
    error: null,
    hasEverOpened: false,
  }

  function refreshSnapshot(): CallFeedStatusEvent {
    currentEvent = { status, attempt, error: lastError, hasEverOpened }
    return currentEvent
  }

  function emitStatus(next: CallFeedStatus, error: CallFeedError | null = lastError): void {
    status = next
    lastError = error
    const event = refreshSnapshot()
    for (const listener of Array.from(statusListeners)) {
      try {
        listener(event)
      } catch {
        // A broken subscriber must not take down the connection.
      }
    }
  }

  function emitMessage(message: CallFeedMessage): void {
    for (const listener of Array.from(messageListeners)) {
      try {
        listener(message)
      } catch {
        // Same: one bad consumer cannot break the feed for the others.
      }
    }
  }

  /** Detach every handler. After this the socket can never call back into us. */
  function detach(target: WebSocketLike | null): void {
    if (!target) return
    target.onopen = null
    target.onclose = null
    target.onerror = null
    target.onmessage = null
  }

  function clearPendingReconnect(): void {
    if (timer !== null) {
      clearTimeoutFn(timer)
      timer = null
    }
  }

  function scheduleReconnect(error: CallFeedError): void {
    if (disposed) return

    attempt += 1

    const handshakeExhausted = !hasEverOpened && attempt >= maxHandshakeAttempts
    if (handshakeExhausted) {
      emitStatus('closed', {
        kind: 'handshake-rejected',
        code: error.code,
        reason: error.reason,
        message: HANDSHAKE_REJECTED_HINT,
      })
      return
    }

    if (attempt > maxReconnectAttempts) {
      emitStatus('closed', {
        kind: 'retries-exhausted',
        code: error.code,
        reason: error.reason,
        message: `Gave up after ${maxReconnectAttempts} reconnect attempts.`,
      })
      return
    }

    const delay = computeBackoffDelay(attempt, options.backoff, random)
    emitStatus('reconnecting', error)

    clearPendingReconnect()
    timer = setTimeoutFn(() => {
      timer = null
      // Belt and braces: close() clears this timer, but if a timer somehow
      // fires after teardown (a fake/immediate timer, a racing scheduler) the
      // tombstone still stops it from opening a socket post-unmount.
      if (disposed) return
      open()
    }, delay)
  }

  function open(): void {
    if (disposed || socket) return

    emitStatus(attempt === 0 ? 'connecting' : 'reconnecting')

    const token = options.token !== undefined ? options.token : readStoredToken()
    const url = options.url ?? callFeedUrl(callId, { baseUrl: options.baseUrl, token, authMode })
    const headers = buildHandshakeHeaders(token)
    const protocols = buildHandshakeProtocols(token, authMode)

    let created: WebSocketLike
    try {
      created = socketFactory(url, headers, protocols)
    } catch (err) {
      scheduleReconnect({
        kind: 'transport-error',
        code: null,
        reason: String(err),
        message: 'WebSocket could not be constructed.',
      })
      return
    }

    socket = created

    // Every handler re-checks `disposed` and identity: a socket that has been
    // replaced or torn down must never mutate current state.
    created.onopen = () => {
      if (disposed || created !== socket) return
      hasEverOpened = true
      attempt = 0
      emitStatus('open', null)
    }

    created.onmessage = (event) => {
      if (disposed || created !== socket) return
      emitMessage(parseCallFeedMessage(event?.data))
    }

    created.onerror = () => {
      if (disposed || created !== socket) return
      // Browsers give no detail on WS errors; the close event that follows
      // carries the actionable code, so we only record here.
      lastError = {
        kind: 'transport-error',
        code: null,
        reason: 'socket error',
        message: 'WebSocket transport error.',
      }
    }

    created.onclose = (event) => {
      if (disposed || created !== socket) return
      detach(created)
      socket = null

      const code = event?.code ?? 1006
      const reason = event?.reason ?? ''

      if (NON_RETRYABLE_CLOSE_CODES.has(code)) {
        emitStatus('closed', {
          kind: code === 1000 ? 'closed-by-server' : 'handshake-rejected',
          code,
          reason,
          message:
            code === 4404
              ? 'Call not found, or outside your access scope (calls.py closes 4404 for both).'
              : code === 1000
                ? 'Server closed the feed normally.'
                : `Connection refused by server (code ${code}).`,
        })
        return
      }

      scheduleReconnect({
        kind: hasEverOpened ? 'closed-by-server' : 'handshake-rejected',
        code,
        reason,
        message: hasEverOpened
          ? `Connection lost (code ${code}).`
          : `Handshake failed (code ${code}). ${HANDSHAKE_REJECTED_HINT}`,
      })
    }
  }

  return {
    callId,

    connect() {
      if (disposed) return
      open()
    },

    /**
     * Full teardown, in this order:
     *   1. tombstone   — any in-flight continuation becomes a no-op
     *   2. clear timer — a queued reconnect can never fire
     *   3. detach      — the socket can never call back
     *   4. close       — release the connection
     *   5. notify then drop subscribers
     *
     * Idempotent. This is the leak class the layer exists to avoid: a reconnect
     * timer firing after the component unmounted, opening an orphan socket that
     * nothing owns and nothing closes.
     */
    close() {
      if (disposed) return
      disposed = true

      clearPendingReconnect()

      const current = socket
      socket = null
      detach(current)
      if (current) {
        try {
          current.close(1000, 'client closed')
        } catch {
          // Closing an already-closing socket is not an error worth surfacing.
        }
      }

      status = 'closed'
      attempt = 0
      const event = refreshSnapshot()
      for (const listener of Array.from(statusListeners)) {
        try {
          listener(event)
        } catch {
          // ignore
        }
      }
      statusListeners.clear()
      messageListeners.clear()
    },

    getStatus() {
      return status
    },

    getStatusEvent() {
      return currentEvent
    },

    onMessage(listener) {
      if (disposed) return () => {}
      messageListeners.add(listener)
      return () => {
        messageListeners.delete(listener)
      }
    },

    /**
     * Subscribe to status. The listener is invoked SYNCHRONOUSLY with the
     * current snapshot before returning, so a subscriber that attaches after
     * the socket already opened is not stranded on a stale initial value —
     * and so React consumers never have to call setState in an effect body to
     * seed themselves.
     */
    onStatusChange(listener) {
      if (disposed) return () => {}
      statusListeners.add(listener)
      try {
        listener(currentEvent)
      } catch {
        // ignore
      }
      return () => {
        statusListeners.delete(listener)
      }
    },
  }
}

/* ────────────────────────────────────────────────────────────────────────
 * Ref-counted registry — React 19 StrictMode safety
 *
 * StrictMode in dev runs mount -> unmount -> mount synchronously. A hook that
 * constructs a socket in an effect and closes it in the cleanup therefore opens
 * TWO sockets per call, and the backend sees two subscribers per viewer.
 *
 * Fix: key live connections by call, ref-count them, and defer teardown by a
 * short grace period. StrictMode's remount lands inside that window, cancels
 * the pending teardown and re-uses the SAME socket — one connection, verified
 * by counting socketFactory invocations rather than by inspection.
 *
 * The same mechanism dedupes genuine concurrent consumers (a transcript pane
 * and a sentiment gauge on one screen share one socket).
 * ──────────────────────────────────────────────────────────────────────── */

interface RegistryEntry {
  feed: CallFeedSocket
  refs: number
  teardown: TimerHandle | null
}

const registry = new Map<string, RegistryEntry>()

/** Long enough to span a StrictMode remount, short enough to free a real leave. */
export const DEFAULT_RELEASE_GRACE_MS = 750

export interface AcquireOptions extends CallFeedSocketOptions {
  /** Distinguishes connections to the same call that need different settings. */
  registryKey?: string
  releaseGraceMs?: number
}

export interface CallFeedLease {
  feed: CallFeedSocket
  /** Idempotent — safe to call from an effect cleanup that runs twice. */
  release: () => void
}

export function acquireCallFeed(callId: string, options: AcquireOptions = {}): CallFeedLease {
  const key = options.registryKey ?? callId
  const grace = options.releaseGraceMs ?? DEFAULT_RELEASE_GRACE_MS
  const setTimeoutFn =
    options.setTimeoutFn ?? (((fn, ms) => setTimeout(fn, ms)) as (fn: () => void, ms: number) => TimerHandle)
  const clearTimeoutFn = options.clearTimeoutFn ?? (((h) => clearTimeout(h)) as (h: TimerHandle) => void)

  let entry = registry.get(key)

  if (entry) {
    // Cancel a teardown that was scheduled by a just-run cleanup.
    if (entry.teardown !== null) {
      clearTimeoutFn(entry.teardown)
      entry.teardown = null
    }
  } else {
    const feed = createCallFeedSocket(callId, options)
    entry = { feed, refs: 0, teardown: null }
    registry.set(key, entry)
    feed.connect()
  }

  const active = entry
  active.refs += 1

  let released = false
  return {
    feed: active.feed,
    release() {
      if (released) return
      released = true
      active.refs -= 1
      if (active.refs > 0) return

      if (active.teardown !== null) clearTimeoutFn(active.teardown)
      active.teardown = setTimeoutFn(() => {
        active.teardown = null
        // A re-acquire during the grace window bumped refs back up — keep it.
        if (active.refs > 0) return
        active.feed.close()
        if (registry.get(key) === active) registry.delete(key)
      }, grace)
    },
  }
}

/** Test/HMR escape hatch — closes and forgets every pooled connection. */
export function resetCallFeedRegistry(): void {
  for (const [key, entry] of Array.from(registry.entries())) {
    if (entry.teardown !== null) clearTimeout(entry.teardown)
    entry.feed.close()
    registry.delete(key)
  }
}
