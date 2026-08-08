/**
 * S24 — AI Playbook configuration.
 *
 * This edits what the AI says to real customers on real phone calls, so the
 * form is deliberately explicit rather than clever:
 *
 *  - It never PUTs a partial object it has not shown you. The whole config is
 *    loaded, edited locally, and sent as one body — a form that silently sends
 *    only "changed" fields will eventually send a field the operator never saw.
 *  - The API strips nulls and 422s an empty body, so an unchanged form cannot
 *    be submitted by accident.
 *  - Nothing is saved until Save is pressed, and the dirty state is visible.
 *    Auto-save on a live call script is not a feature.
 *
 * The first language in the array is the DEFAULT — reordering changes
 * behaviour, so the order is shown and controllable rather than sorted for
 * cosmetic tidiness.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { aiConfigApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { hasRole } from '../../lib/rbac'
import { useAuth } from '../../lib/auth'
import { NoAccess } from '../../components/RequireRole'
import { ErrorState, SkeletonRows } from '../../components/DataState'
import type { AiConfig, AiConfigQuestion } from '../../types/travel'

const KNOWN_LANGUAGES = ['en', 'hi', 'te', 'ta', 'kn', 'ml', 'mr', 'bn']

export default function AiConfigPage() {
  const { me } = useAuth()
  const canEdit = hasRole(me?.user, 'manager')

  const configQ = useQuery({ queryKey: ['ai-config'], queryFn: aiConfigApi.get })

  if (!canEdit) {
    return (
      <>
        <div className="topbar"><div className="page-title">AI Playbook</div></div>
        <div className="content"><NoAccess what="the AI playbook" /></div>
      </>
    )
  }

  if (configQ.isLoading) {
    return (
      <>
        <div className="topbar"><div className="page-title">AI Playbook</div></div>
        <div className="content"><SkeletonRows rows={6} height={52} /></div>
      </>
    )
  }

  if (configQ.isError || !configQ.data) {
    return (
      <>
        <div className="topbar"><div className="page-title">AI Playbook</div></div>
        <div className="content">
          <ErrorState error={configQ.error} onRetry={() => configQ.refetch()} />
        </div>
      </>
    )
  }

  // Keyed on `updated_at`: a fresh server version remounts the form with the
  // new values as its initial state. This is React's own answer to "reset state
  // when data changes" — seeding through an effect renders twice and can
  // clobber an edit that is mid-keystroke.
  return <AiConfigForm key={configQ.data.updated_at} config={configQ.data} />
}

function AiConfigForm({ config }: { config: AiConfig }) {
  const queryClient = useQueryClient()

  const [questions, setQuestions] = useState<AiConfigQuestion[]>(config.question_flow ?? [])
  const [languages, setLanguages] = useState<string[]>(config.languages ?? [])
  const [persona, setPersona] = useState({
    name: config.voice_persona?.name ?? '',
    tone: config.voice_persona?.tone ?? '',
    greeting: config.voice_persona?.greeting ?? '',
  })
  const [hours, setHours] = useState({
    start: config.working_hours?.start ?? '',
    end: config.working_hours?.end ?? '',
    timezone: config.working_hours?.timezone ?? 'Asia/Kolkata',
  })
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: () =>
      aiConfigApi.update({
        question_flow: questions,
        languages,
        voice_persona: persona,
        working_hours: hours,
      }),
    onMutate: () => {
      setError(null)
      setSaved(false)
    },
    onSuccess: () => {
      setSaved(true)
      setDirty(false)
      queryClient.invalidateQueries({ queryKey: ['ai-config'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function touch<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v)
      setDirty(true)
      setSaved(false)
    }
  }

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">AI Playbook</div>
          <div className="page-sub">
            What the AI asks and how it sounds on live calls
            {dirty && ' · unsaved changes'}
          </div>
        </div>
        <div className="toolbar">
          <button
            type="button"
            className="btn"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      <div className="content">
        {error && <div className="error-banner" role="alert">{error}</div>}
        {saved && <div className="conn-banner ok" role="status">Configuration saved.</div>}

        <>
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-head">
                <div className="t2">Question flow</div>
                <button
                  type="button"
                  className="btn-secondary sm"
                  onClick={() =>
                    touch(setQuestions)([
                      ...questions,
                      { order: questions.length + 1, question: '', field: '' },
                    ])
                  }
                >
                  Add question
                </button>
              </div>

              {questions.length === 0 ? (
                <p className="state-reason" style={{ margin: 0 }}>
                  No questions configured. The AI will not gather structured details.
                </p>
              ) : (
                <div className="question-list">
                  {questions.map((q, i) => (
                    <div key={i} className="question-row">
                      <span className="question-order">{i + 1}</span>
                      <input
                        className="input grow"
                        placeholder="What should the AI ask?"
                        value={q.question}
                        onChange={(e) =>
                          touch(setQuestions)(
                            questions.map((x, j) =>
                              j === i ? { ...x, question: e.target.value } : x,
                            ),
                          )
                        }
                      />
                      <input
                        className="input"
                        placeholder="field name"
                        value={q.field}
                        onChange={(e) =>
                          touch(setQuestions)(
                            questions.map((x, j) => (j === i ? { ...x, field: e.target.value } : x)),
                          )
                        }
                      />
                      <button
                        type="button"
                        className="btn-secondary sm"
                        onClick={() =>
                          touch(setQuestions)(
                            questions
                              .filter((_, j) => j !== i)
                              .map((x, j) => ({ ...x, order: j + 1 })),
                          )
                        }
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="grid-2">
              <div className="card">
                <div className="t2" style={{ marginBottom: 12 }}>Languages</div>
                <p className="panel-footnote" style={{ marginBottom: 10 }}>
                  The first is the default. Order is behaviour, not presentation.
                </p>
                <div className="lang-chips">
                  {KNOWN_LANGUAGES.map((code) => {
                    const idx = languages.indexOf(code)
                    const on = idx !== -1
                    return (
                      <button
                        key={code}
                        type="button"
                        className={`lang-chip${on ? ' on' : ''}${idx === 0 ? ' primary' : ''}`}
                        onClick={() =>
                          touch(setLanguages)(
                            on ? languages.filter((l) => l !== code) : [...languages, code],
                          )
                        }
                      >
                        {code}
                        {idx === 0 && <span className="chip-tag">default</span>}
                      </button>
                    )
                  })}
                </div>
                {languages.length === 0 && (
                  <p className="takeover-note warn">
                    No language selected — the backend will fall back to its own default.
                  </p>
                )}
              </div>

              <div className="card">
                <div className="t2" style={{ marginBottom: 12 }}>Voice &amp; hours</div>
                <div className="form-stack">
                  <label className="stack-field">
                    <span>Persona name</span>
                    <input
                      className="input"
                      value={persona.name}
                      onChange={(e) => touch(setPersona)({ ...persona, name: e.target.value })}
                    />
                  </label>
                  <label className="stack-field">
                    <span>Tone</span>
                    <input
                      className="input"
                      value={persona.tone}
                      onChange={(e) => touch(setPersona)({ ...persona, tone: e.target.value })}
                    />
                  </label>
                  <label className="stack-field">
                    <span>Greeting</span>
                    <textarea
                      className="input"
                      rows={2}
                      value={persona.greeting}
                      onChange={(e) => touch(setPersona)({ ...persona, greeting: e.target.value })}
                    />
                  </label>
                  <div className="form-row">
                    <label className="stack-field">
                      <span>Opens</span>
                      <input
                        className="input"
                        type="time"
                        value={hours.start}
                        onChange={(e) => touch(setHours)({ ...hours, start: e.target.value })}
                      />
                    </label>
                    <label className="stack-field">
                      <span>Closes</span>
                      <input
                        className="input"
                        type="time"
                        value={hours.end}
                        onChange={(e) => touch(setHours)({ ...hours, end: e.target.value })}
                      />
                    </label>
                    <label className="stack-field">
                      <span>Timezone</span>
                      <input
                        className="input"
                        value={hours.timezone}
                        onChange={(e) => touch(setHours)({ ...hours, timezone: e.target.value })}
                      />
                    </label>
                  </div>
                </div>
              </div>
            </div>
        </>
      </div>
    </>
  )
}
