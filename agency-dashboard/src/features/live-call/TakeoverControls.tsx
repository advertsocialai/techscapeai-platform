/**
 * S11 — takeover controls for a live call.
 *
 * THE ONE RULE THIS FILE EXISTS TO ENFORCE: the displayed state comes from the
 * `takeover_state` WebSocket broadcast, never from local optimistic state.
 *
 * This is a correctness constraint, not a UX preference. An operator who
 * believes they have taken over a call, but has not, will start talking over an
 * AI that is still speaking to the customer. The POST response is deliberately
 * NOT used to drive the display either — `CallOut` carries no `takeover_state`
 * field, so there is nothing truthful to read from it.
 *
 * While a request is in flight we show "requesting…" — an explicitly pending
 * state, distinct from both the old and the new state. Guessing the outcome is
 * the failure mode.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { takeoverApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { isReadOnly } from '../../lib/rbac'
import { useAuth } from '../../lib/auth'
import type { TakeoverState } from '../../types/ws'
import {
  ACTION_TARGET,
  LIVE_AUDIO_AVAILABLE,
  LIVE_AUDIO_NOTICE,
  TAKEOVER_ACTIONS,
  canPerform,
  type TakeoverAction,
} from './takeoverMachine'

const STATE_LABEL: Record<TakeoverState, string> = {
  ai: 'AI handling',
  monitoring: 'You are monitoring',
  coaching: 'You are coaching',
  human: 'You have the call',
}

const STATE_COLOR: Record<TakeoverState, string> = {
  ai: 'var(--blue)',
  monitoring: 'var(--amber)',
  coaching: 'var(--amber)',
  human: 'var(--green)',
}

export default function TakeoverControls({
  callId,
  /**
   * Confirmed state from the WS broadcast. `null` means no broadcast has
   * arrived yet this session — which is NOT the same as "ai", so it renders as
   * unknown rather than defaulting to a state we have not been told.
   */
  confirmed,
  isStale,
  callIsActive,
}: {
  callId: string
  confirmed: TakeoverState | null
  isStale: boolean
  callIsActive: boolean
}) {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const [pending, setPending] = useState<TakeoverAction | null>(null)
  const [confirming, setConfirming] = useState<TakeoverAction | null>(null)
  const [error, setError] = useState<string | null>(null)

  const readOnly = isReadOnly(me?.user)

  const mutation = useMutation({
    mutationFn: (action: TakeoverAction) => {
      if (action === 'monitor') return takeoverApi.monitor(callId)
      if (action === 'barge') return takeoverApi.barge(callId)
      if (action === 'full') return takeoverApi.full(callId)
      return takeoverApi.release(callId)
    },
    onMutate: (action) => {
      setError(null)
      setPending(action)
      // Deliberately NO optimistic cache write. See the file header.
    },
    onError: (err) => setError(errorMessage(err)),
    onSettled: () => {
      setPending(null)
      // The authoritative display still comes from WS; this only refreshes the
      // REST view of the call (status, mode) that sits alongside it.
      queryClient.invalidateQueries({ queryKey: ['calls', 'live'] })
    },
  })

  function run(action: TakeoverAction) {
    const meta = TAKEOVER_ACTIONS.find((a) => a.action === action)
    if (meta?.highConsequence && confirming !== action) {
      setConfirming(action)
      return
    }
    setConfirming(null)
    mutation.mutate(action)
  }

  return (
    <div className="card takeover-panel">
      <div className="takeover-head">
        <div className="t2">Takeover</div>
        <span
          className="takeover-state"
          style={{ color: confirmed ? STATE_COLOR[confirmed] : 'var(--text-dim)' }}
        >
          {pending
            ? 'requesting…'
            : confirmed
              ? STATE_LABEL[confirmed]
              : 'state unknown'}
        </span>
      </div>

      {/* An unknown state is worth saying out loud: the buttons below are
          disabled because we genuinely do not know what is legal, not because
          the feature is off. */}
      {!confirmed && !pending && (
        <p className="takeover-note">
          No takeover broadcast received yet for this call. Controls stay disabled until the
          server tells us the current state — acting on a guess could mute an AI mid-sentence.
        </p>
      )}

      {isStale && (
        <p className="takeover-note warn">
          Live feed disconnected — the state shown may be out of date.
        </p>
      )}

      {!LIVE_AUDIO_AVAILABLE && <p className="takeover-note">{LIVE_AUDIO_NOTICE}</p>}

      {readOnly && (
        <p className="takeover-note">Your role is read-only, so takeover actions are unavailable.</p>
      )}

      <div className="takeover-actions">
        {TAKEOVER_ACTIONS.map((meta) => {
          const legal = confirmed ? canPerform(confirmed, meta.action) : false
          const disabled =
            readOnly || !callIsActive || !confirmed || !legal || pending !== null
          return (
            <button
              key={meta.action}
              type="button"
              className={`btn takeover-btn${meta.highConsequence ? ' danger' : ''}`}
              disabled={disabled}
              title={
                !callIsActive
                  ? 'The call is not active'
                  : confirmed && !legal
                    ? `Not allowed from "${confirmed}" — the server would reject this`
                    : meta.effect
              }
              onClick={() => run(meta.action)}
            >
              {pending === meta.action ? '…' : meta.label}
            </button>
          )
        })}
      </div>

      {confirming && (
        <div className="takeover-confirm" role="alertdialog">
          <p className="state-title">
            {TAKEOVER_ACTIONS.find((a) => a.action === confirming)?.label} this call?
          </p>
          <p className="state-reason">
            {TAKEOVER_ACTIONS.find((a) => a.action === confirming)?.effect} The customer is on the
            line right now.
          </p>
          <div className="takeover-confirm-actions">
            <button type="button" className="btn danger" onClick={() => run(confirming)}>
              Yes, {TAKEOVER_ACTIONS.find((a) => a.action === confirming)?.label.toLowerCase()}
            </button>
            <button type="button" className="btn-secondary" onClick={() => setConfirming(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="takeover-note warn" role="alert">
          {error}
          {/* A 409 is the state machine refusing, not a transient fault — say so
              rather than inviting a blind retry. */}
        </p>
      )}

      {confirmed && (
        <p className="takeover-legal">
          Allowed from <strong>{confirmed}</strong>:{' '}
          {TAKEOVER_ACTIONS.filter((a) => canPerform(confirmed, a.action))
            .map((a) => a.label)
            .join(', ') || 'nothing'}
          {' · '}
          targets: {Object.entries(ACTION_TARGET)
            .filter(([action]) => canPerform(confirmed, action as TakeoverAction))
            .map(([, target]) => target)
            .join(', ') || '—'}
        </p>
      )}
    </div>
  )
}
