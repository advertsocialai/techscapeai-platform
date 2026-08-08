/**
 * Follow-up ladder editor.
 *
 * Editing a rule changes when future follow-ups fire. The backend cascades to
 * FUTURE-scheduled rows only and returns `rescheduled` — a count of how many it
 * moved. That count is surfaced after every save, because "saved" alone hides
 * the blast radius: a operator who nudges a day-3 rule and silently reschedules
 * 200 pending follow-ups has done something much bigger than they think.
 *
 * Rows already due, overdue, in progress or done are provably untouched. Said
 * on screen, since the natural fear is that an edit reshuffles work someone is
 * mid-way through.
 *
 * `ladder_day` is constrained to 1 | 3 | 7 by the type — the backend's ladder
 * has exactly three rungs, so this is a select, not a free number input that
 * would 422.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { followUpsApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import type {
  FollowUpChannel,
  FollowUpRule,
  FollowUpType,
  LadderDay,
} from '../../types/travel'

const LADDER_DAYS: LadderDay[] = [1, 3, 7]
const TYPES: FollowUpType[] = ['nudge', 'summary', 'personal_call', 'price_alert']
const CHANNELS: FollowUpChannel[] = ['whatsapp', 'sms', 'email', 'call', 'in_app']

export default function LadderEditor({
  rules,
  readOnly,
}: {
  rules: FollowUpRule[]
  readOnly: boolean
}) {
  const queryClient = useQueryClient()

  const [day, setDay] = useState<LadderDay>(1)
  const [type, setType] = useState<FollowUpType>('nudge')
  const [channel, setChannel] = useState<FollowUpChannel>('whatsapp')
  const [offset, setOffset] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<string | null>(null)

  const upsert = useMutation({
    mutationFn: () =>
      followUpsApi.upsertRule({
        ladder_day: day,
        type,
        channel,
        // Empty means "derive as ladder_day × 24h" — null, not 0, which would
        // mean "fire immediately".
        due_offset_hours: offset.trim() === '' ? null : Number(offset),
      }),
    onMutate: () => {
      setError(null)
      setResult(null)
    },
    onSuccess: (res) => {
      setResult(
        res.rescheduled > 0
          ? `Saved. ${res.rescheduled} future follow-up${res.rescheduled === 1 ? ' was' : 's were'} rescheduled. Nothing already due or in progress was moved.`
          : 'Saved. No scheduled follow-ups needed moving.',
      )
      queryClient.invalidateQueries({ queryKey: ['follow-ups'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const toggleActive = useMutation({
    mutationFn: (rule: FollowUpRule) =>
      followUpsApi.upsertRule({
        ladder_day: rule.ladder_day,
        type: rule.type,
        channel: rule.channel,
        due_offset_hours: rule.due_offset_hours,
        is_active: !rule.is_active,
      }),
    onSuccess: (res) => {
      setResult(
        `Rule ${res.rule.is_active ? 'enabled' : 'disabled'}. ${res.rescheduled} future follow-up${res.rescheduled === 1 ? '' : 's'} affected.`,
      )
      queryClient.invalidateQueries({ queryKey: ['follow-ups'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (readOnly) {
    return (
      <p className="state-reason" style={{ margin: 0 }}>
        Your role is read-only, so ladder rules cannot be edited.
      </p>
    )
  }

  return (
    <>
      <p className="state-reason" style={{ marginBottom: 12 }}>
        Editing a rule reschedules <strong>future</strong> follow-ups only. Anything already due,
        overdue, in progress or done keeps its timing — a rule change cannot move work someone is
        already acting on.
      </p>

      {error && <div className="error-banner" role="alert">{error}</div>}
      {result && <div className="conn-banner ok" role="status">{result}</div>}

      <div className="form-row" style={{ marginBottom: 12 }}>
        <select
          className="input"
          value={day}
          onChange={(e) => setDay(Number(e.target.value) as LadderDay)}
          aria-label="Ladder day"
        >
          {LADDER_DAYS.map((d) => <option key={d} value={d}>Day {d}</option>)}
        </select>
        <select
          className="input"
          value={type}
          onChange={(e) => setType(e.target.value as FollowUpType)}
          aria-label="Follow-up type"
        >
          {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select
          className="input"
          value={channel}
          onChange={(e) => setChannel(e.target.value as FollowUpChannel)}
          aria-label="Channel"
        >
          {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <input
          className="input"
          placeholder="Offset hours (blank = day × 24)"
          inputMode="numeric"
          value={offset}
          onChange={(e) => setOffset(e.target.value)}
        />
        <button
          type="button"
          className="btn"
          disabled={upsert.isPending}
          onClick={() => upsert.mutate()}
        >
          {upsert.isPending ? 'Saving…' : 'Save rule'}
        </button>
      </div>

      {rules.length === 0 ? (
        <p className="state-reason" style={{ margin: 0 }}>
          No ladder rules configured. New leads will not get automatic follow-ups.
        </p>
      ) : (
        <ul className="rule-list">
          {rules.map((r) => (
            <li key={r.id} className={`rule-item${r.is_active ? '' : ' rule-off'}`}>
              <span>Day {r.ladder_day}</span>
              <span className="muted-count">{r.type} · {r.channel}</span>
              <span className="muted-count">
                {r.due_offset_hours != null ? `+${r.due_offset_hours}h` : `+${r.ladder_day * 24}h (derived)`}
              </span>
              <button
                type="button"
                className="btn-secondary sm"
                disabled={toggleActive.isPending}
                onClick={() => toggleActive.mutate(r)}
              >
                {r.is_active ? 'Disable' : 'Enable'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
