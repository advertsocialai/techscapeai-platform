/**
 * takeoverMachine — the client mirror of `VALID_TRANSITIONS` in
 * api/app/services/travel/takeover_service.py:34.
 *
 * There is no runtime link between the two tables; this suite is the link
 * (same pattern as passwordValidation.test.ts). If the backend machine
 * changes and this file does not, drift shows up here instead of as a 409 on
 * a live call.
 */
import { describe, expect, it } from 'vitest'

import {
  ACTION_TARGET,
  TAKEOVER_ACTIONS,
  VALID_TRANSITIONS,
  canPerform,
  canTransition,
  type TakeoverAction,
} from './takeoverMachine'
import type { TakeoverState } from '../../types/ws'

const STATES: TakeoverState[] = ['ai', 'monitoring', 'coaching', 'human']

describe('the transition table mirrors takeover_service.py verbatim', () => {
  it('matches the backend table exactly', () => {
    expect(VALID_TRANSITIONS).toEqual({
      ai: ['monitoring', 'coaching', 'human'],
      monitoring: ['coaching', 'human', 'ai'],
      coaching: ['human', 'ai'],
      human: ['ai'],
    })
  })

  it('no state may transition to itself', () => {
    for (const s of STATES) {
      expect(canTransition(s, s), `${s} -> ${s}`).toBe(false)
    }
  })

  it('escalation is always legal; de-escalation only ever lands on ai', () => {
    const rank: Record<TakeoverState, number> = {
      ai: 0, monitoring: 1, coaching: 2, human: 3,
    }
    for (const from of STATES) {
      for (const to of STATES) {
        if (from === to) continue
        if (rank[to] > rank[from]) {
          expect(canTransition(from, to), `${from} -> ${to}`).toBe(true)
        } else {
          // stepping down skips intermediate states: it must go straight to ai
          expect(canTransition(from, to), `${from} -> ${to}`).toBe(to === 'ai')
        }
      }
    }
  })

  it('unknown states are refused, not crashed on', () => {
    expect(canTransition('rebooting' as TakeoverState, 'ai')).toBe(false)
  })
})

describe('actions', () => {
  it('every action maps to a real state and has UI metadata', () => {
    const actions = TAKEOVER_ACTIONS.map((a) => a.action)
    expect(actions).toEqual(['monitor', 'barge', 'full', 'release'])
    for (const a of TAKEOVER_ACTIONS) {
      expect(STATES).toContain(ACTION_TARGET[a.action])
      expect(a.label).toBeTruthy()
      expect(a.effect).toBeTruthy()
    }
  })

  it('exactly one action is high-consequence: handing the call to a human', () => {
    const high = TAKEOVER_ACTIONS.filter((a) => a.highConsequence)
    expect(high).toHaveLength(1)
    expect(high[0].action).toBe('full')
  })

  it('canPerform agrees with the table for every state x action pair', () => {
    const expected: Record<TakeoverState, TakeoverAction[]> = {
      ai: ['monitor', 'barge', 'full'],
      monitoring: ['barge', 'full', 'release'],
      coaching: ['full', 'release'],
      human: ['release'],
    }
    for (const from of STATES) {
      for (const a of ['monitor', 'barge', 'full', 'release'] as TakeoverAction[]) {
        expect(canPerform(from, a), `${from} x ${a}`).toBe(
          expected[from].includes(a),
        )
      }
    }
  })
})
