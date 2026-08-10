/**
 * S1 — Journey Board. Leads as a kanban across the lifecycle.
 *
 * Drag-to-move IS optimistic, and that is the correct call here: moving a lead
 * between columns is low-consequence and reversible, so waiting on a round-trip
 * would make the board feel broken. Rollback on failure is therefore
 * mandatory — the cache snapshot in `onMutate` is what makes the optimism
 * honest rather than a lie that happens to usually be true.
 *
 * Contrast with takeover (S11), which is never optimistic. The difference is
 * consequence, not consistency for its own sake.
 *
 * Implemented with the HTML5 drag-and-drop API rather than a library: it is one
 * dependency we do not need, and the interaction is a single drop target per
 * column. Keyboard users get a select-based fallback on each card, because
 * native DnD is not keyboard accessible.
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { leadsApi } from '../../lib/api'
import { errorMessage } from '../../lib/errors'
import { isReadOnly } from '../../lib/rbac'
import { useAuth } from '../../lib/auth'
import { ErrorState, SkeletonRows } from '../../components/DataState'
import { formatMoney } from '../../lib/money'
import type { Lead, LeadQualification, LeadStatus } from '../../types/travel'

const COLUMNS: { status: LeadStatus; label: string }[] = [
  { status: 'new', label: 'New' },
  { status: 'qualified', label: 'Qualified' },
  { status: 'itinerary_sent', label: 'Itinerary sent' },
  { status: 'negotiating', label: 'Negotiating' },
  { status: 'booked', label: 'Booked' },
  { status: 'lost', label: 'Lost' },
]

const QUALIFICATIONS: LeadQualification[] = ['cold', 'warm', 'hot', 'converted', 'lost']

export default function JourneyBoardPage() {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const readOnly = isReadOnly(me?.user)

  const [search, setSearch] = useState('')
  const [qualification, setQualification] = useState<LeadQualification | ''>('')
  const [dragOver, setDragOver] = useState<LeadStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  const leadsQ = useQuery({ queryKey: ['leads'], queryFn: () => leadsApi.list() })

  const move = useMutation({
    mutationFn: ({ id, status }: { id: string; status: LeadStatus }) =>
      leadsApi.updateStatus(id, status),

    onMutate: async ({ id, status }) => {
      setError(null)
      // Stop an in-flight refetch from resurrecting the pre-drag value on top
      // of the optimistic write.
      await queryClient.cancelQueries({ queryKey: ['leads'] })
      const previous = queryClient.getQueryData<Lead[]>(['leads'])
      queryClient.setQueryData<Lead[]>(['leads'], (old) =>
        (old ?? []).map((l) => (l.id === id ? { ...l, status } : l)),
      )
      return { previous }
    },

    // The rollback that makes the optimism legitimate.
    onError: (err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(['leads'], context.previous)
      setError(errorMessage(err))
    },

    onSettled: () => queryClient.invalidateQueries({ queryKey: ['leads'] }),
  })

  // Stable identity: `leadsQ.data ?? []` allocates a fresh array on every
  // render, which would change the deps of both useMemos below every time and
  // silently defeat the memoisation they exist for.
  const leadsData = leadsQ.data
  const leads = useMemo(() => leadsData ?? [], [leadsData])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return leads.filter((l) => {
      if (qualification && l.qualification !== qualification) return false
      if (!q) return true
      return (
        l.raw_message?.toLowerCase().includes(q) ||
        l.destination_hint?.toLowerCase().includes(q) ||
        l.intent?.toLowerCase().includes(q) ||
        l.id.toLowerCase().startsWith(q)
      )
    })
  }, [leads, search, qualification])

  const byStatus = useMemo(() => {
    const map = new Map<LeadStatus, Lead[]>()
    COLUMNS.forEach((c) => map.set(c.status, []))
    filtered.forEach((l) => map.get(l.status)?.push(l))
    return map
  }, [filtered])

  const isFiltered = search.trim() !== '' || qualification !== ''

  function drop(status: LeadStatus, e: React.DragEvent) {
    e.preventDefault()
    setDragOver(null)
    const id = e.dataTransfer.getData('text/plain')
    if (!id) return
    const lead = leads.find((l) => l.id === id)
    if (!lead || lead.status === status) return
    move.mutate({ id, status })
  }

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Journey Board</div>
          <div className="page-sub">
            {filtered.length} of {leads.length} leads
            {isFiltered && ' · filtered'}
          </div>
        </div>
        <div className="toolbar">
          <input
            className="input"
            placeholder="Search destination, intent, message…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select aria-label="Filter by qualification"
            className="input"
            value={qualification}
            onChange={(e) => setQualification(e.target.value as LeadQualification | '')}
          >
            <option value="">All qualifications</option>
            {QUALIFICATIONS.map((q) => (
              <option key={q} value={q}>{q}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="content">
        {error && <div className="error-banner" role="alert">{error}</div>}

        {leadsQ.isLoading ? (
          <SkeletonRows rows={4} height={90} />
        ) : leadsQ.isError ? (
          <ErrorState error={leadsQ.error} onRetry={() => leadsQ.refetch()} />
        ) : (
          <div className="kanban">
            {COLUMNS.map((col) => {
              const items = byStatus.get(col.status) ?? []
              return (
                <div
                  key={col.status}
                  className={`kan-col${dragOver === col.status ? ' drag-over' : ''}`}
                  onDragOver={(e) => {
                    if (readOnly) return
                    e.preventDefault()
                    setDragOver(col.status)
                  }}
                  onDragLeave={() => setDragOver(null)}
                  onDrop={(e) => !readOnly && drop(col.status, e)}
                >
                  <div className="kan-header">
                    <span>{col.label}</span>
                    <span className="muted-count">{items.length}</span>
                  </div>

                  {items.length === 0 ? (
                    // "Nothing here" and "nothing matches your filter" send the
                    // user to completely different next actions.
                    <p className="kan-empty">
                      {isFiltered ? 'None match the filter' : 'Empty'}
                    </p>
                  ) : (
                    items.map((lead) => (
                      <article
                        key={lead.id}
                        className="kan-card"
                        draggable={!readOnly}
                        onDragStart={(e) => e.dataTransfer.setData('text/plain', lead.id)}
                      >
                        <Link to={`/journey-board/${lead.id}`} className="kan-card-link">
                          <div className="kan-card-title">
                            {lead.destination_hint || lead.intent || 'Untitled lead'}
                          </div>
                          <p className="kan-card-msg">{lead.raw_message}</p>
                        </Link>

                        <div className="kan-card-meta">
                          <span className={`badge qual-${lead.qualification}`}>
                            {lead.qualification}
                          </span>
                          {lead.budget_inr != null && (
                            <span className="muted-count">
                              {formatMoney(lead.budget_inr, 'INR')}
                            </span>
                          )}
                        </div>

                        {/* Native drag-and-drop is not keyboard accessible, so
                            the same action is always reachable from a select. */}
                        {!readOnly && (
                          <select
                            className="kan-move"
                            value={lead.status}
                            aria-label={`Move lead to another stage`}
                            onChange={(e) =>
                              move.mutate({ id: lead.id, status: e.target.value as LeadStatus })
                            }
                          >
                            {COLUMNS.map((c) => (
                              <option key={c.status} value={c.status}>{c.label}</option>
                            ))}
                          </select>
                        )}
                      </article>
                    ))
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </>
  )
}
