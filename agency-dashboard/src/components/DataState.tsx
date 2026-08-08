/**
 * The three states every data surface owes the user: loading, empty, error.
 *
 * Two conventions are enforced here rather than left to each screen:
 *
 *  1. Loading is a SKELETON shaped like the eventual content, not a spinner.
 *     A spinner says "something is happening"; a skeleton says "a table with
 *     roughly this many rows is arriving", which is the information the user
 *     actually wants while waiting.
 *
 *  2. Empty must never look like loading, and must say WHY it is empty. "No
 *     leads" and "No leads matching these filters" send the user to completely
 *     different next actions, and a screen that renders the first when it means
 *     the second sends them looking for a bug that isn't there.
 *
 * Errors always carry a retry. A dead end with no way forward turns a transient
 * 502 into a reload of the whole app.
 */
import type { ReactNode } from 'react'
import { errorMessage } from '../lib/errors'

export function Skeleton({
  width = '100%',
  height = 14,
  radius = 6,
}: {
  width?: number | string
  height?: number | string
  radius?: number
}) {
  return (
    <span
      className="skeleton"
      aria-hidden="true"
      style={{ width, height, borderRadius: radius }}
    />
  )
}

/** A skeleton block shaped like a list/table of `rows` rows. */
export function SkeletonRows({ rows = 5, height = 44 }: { rows?: number; height?: number }) {
  return (
    <div className="skeleton-rows" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} height={height} radius={8} />
      ))}
    </div>
  )
}

/** A skeleton block shaped like a row of stat cards. */
export function SkeletonCards({ count = 4, height = 92 }: { count?: number; height?: number }) {
  return (
    <div className="skeleton-cards" role="status" aria-label="Loading">
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} height={height} radius={12} />
      ))}
    </div>
  )
}

export function EmptyState({
  title,
  reason,
  action,
}: {
  title: string
  /** Why it is empty — "nothing yet" vs "nothing matches your filters". Required on purpose. */
  reason: string
  action?: ReactNode
}) {
  return (
    <div className="state-block">
      <p className="state-title">{title}</p>
      <p className="state-reason">{reason}</p>
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="state-block state-error" role="alert">
      <p className="state-title">Could not load this</p>
      <p className="state-reason">{errorMessage(error)}</p>
      {onRetry && (
        <button type="button" className="btn-secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

/**
 * Convenience wrapper for the common TanStack Query shape. Screens with a
 * bespoke skeleton should compose the pieces above directly instead.
 */
export function QueryState({
  isLoading,
  error,
  isEmpty,
  emptyTitle = 'Nothing here yet',
  emptyReason,
  onRetry,
  skeleton,
  children,
}: {
  isLoading: boolean
  error: unknown
  isEmpty?: boolean
  emptyTitle?: string
  emptyReason?: string
  onRetry?: () => void
  skeleton?: ReactNode
  children: ReactNode
}) {
  if (isLoading) return <>{skeleton ?? <SkeletonRows />}</>
  if (error) return <ErrorState error={error} onRetry={onRetry} />
  if (isEmpty) {
    return (
      <EmptyState
        title={emptyTitle}
        reason={emptyReason ?? 'No records have been created yet.'}
      />
    )
  }
  return <>{children}</>
}
