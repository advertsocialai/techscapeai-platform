/**
 * Client-side mirror of the backend takeover state machine.
 *
 * Source: `VALID_TRANSITIONS` in
 * `api/app/services/travel/takeover_service.py:34`. Kept in sync by hand — if
 * the two ever disagree, the BACKEND wins and this file is the bug: the server
 * calls `_assert_transition` and returns 409, so a button this file thinks is
 * legal simply fails. That failure mode is the safe direction, which is why the
 * UI never treats this table as permission to skip handling a 409.
 *
 * What this is FOR: disabling buttons that provably cannot work, so an operator
 * on a live call isn't invited to click something that will 409. It is not a
 * guarantee and it is not security.
 */
import type { TakeoverState } from '../../types/ws'

/** `takeover_service.py:34` — copied verbatim. */
export const VALID_TRANSITIONS: Record<TakeoverState, TakeoverState[]> = {
  ai: ['monitoring', 'coaching', 'human'],
  monitoring: ['coaching', 'human', 'ai'],
  coaching: ['human', 'ai'],
  human: ['ai'],
}

/** The four takeover endpoints, and the state each one lands in. */
export type TakeoverAction = 'monitor' | 'barge' | 'full' | 'release'

export const ACTION_TARGET: Record<TakeoverAction, TakeoverState> = {
  monitor: 'monitoring',
  barge: 'coaching',
  full: 'human',
  release: 'ai',
}

export function canTransition(from: TakeoverState, to: TakeoverState): boolean {
  return VALID_TRANSITIONS[from]?.includes(to) ?? false
}

export function canPerform(from: TakeoverState, action: TakeoverAction): boolean {
  return canTransition(from, ACTION_TARGET[action])
}

export interface TakeoverActionMeta {
  action: TakeoverAction
  label: string
  /** What actually happens on the phone call. Shown as the button's title. */
  effect: string
  /**
   * True for the action that hands the live customer to a human. It gets a
   * confirmation dialog; the others deliberately do not, because confirming
   * everything trains people to click through confirmations.
   */
  highConsequence: boolean
}

export const TAKEOVER_ACTIONS: TakeoverActionMeta[] = [
  {
    action: 'monitor',
    label: 'Monitor',
    effect: 'Join the call silently. The customer and the AI hear nothing from you.',
    highConsequence: false,
  },
  {
    action: 'barge',
    label: 'Coach',
    effect: 'Speak on the call alongside the AI. The customer hears you.',
    highConsequence: false,
  },
  {
    action: 'full',
    label: 'Take over',
    effect: 'Mute the AI and handle the call yourself. The AI stops speaking.',
    highConsequence: true,
  },
  {
    action: 'release',
    label: 'Release to AI',
    effect: 'Hand the call back. The AI resumes speaking to the customer.',
    highConsequence: false,
  },
]

/**
 * 📞 Live audio is NOT wired — Plivo MPC is not active (Phase 2B never ran, no
 * Plivo credentials). The state machine, the DB writes and the WS broadcast all
 * work; joining the actual audio does not. See `BLOCKERS.md` B-P3-01.
 *
 * Surfaced in the UI rather than left as a comment, because an operator who
 * clicks "Monitor" and hears silence will assume the feature is broken instead
 * of unprovisioned.
 */
export const LIVE_AUDIO_AVAILABLE = false

export const LIVE_AUDIO_NOTICE =
  'Call state changes are live, but audio bridging is not provisioned yet — you will not hear ' +
  'the call. Tracked as B-P3-01.'
