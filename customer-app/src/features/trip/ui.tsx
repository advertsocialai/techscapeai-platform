/**
 * Shared primitives for the traveller screens.
 *
 * `Money` requires a currency and there is no bare-amount variant — the same
 * rule the agency dashboard enforces, for the same reason. A customer looking
 * at their own booking is the last place an unlabelled figure belongs.
 */
import type { ReactNode } from 'react'

import { colors, radii } from '../../styles/tokens'

export function Card({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        background: colors.surface,
        border: `1px solid ${colors.surfaceBorder}`,
        borderRadius: radii.card,
        padding: '20px 18px',
        marginBottom: 14,
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05)',
        backdropFilter: 'blur(20px)',
      }}
    >
      {children}
    </div>
  )
}

/**
 * Format an amount with its currency. Kept as a plain function so the
 * try/catch wraps only the formatting — building JSX inside a try/catch would
 * not actually catch a render error, since React renders later.
 */
function formatMoney(amount: string, currency: string): string {
  const n = Number(amount)
  if (!Number.isFinite(n)) return '—'
  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(n)
  } catch {
    // Unknown ISO code — still print the code so the figure stays unambiguous.
    return `${n.toLocaleString('en-IN')} ${currency}`
  }
}

/** Amount + currency, together, always. */
export function Money({ amount, currency }: { amount: string; currency: string }) {
  return <>{formatMoney(amount, currency)}</>
}

/** Shaped like the cards it replaces, not a spinner. */
export function SkeletonBlock({ rows = 3 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" style={{ display: 'grid', gap: 14 }}>
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          style={{
            height: i === 0 ? 130 : 90,
            borderRadius: radii.card,
            background: colors.surface,
            border: `1px solid ${colors.surfaceBorder}`,
          }}
        />
      ))}
    </div>
  )
}

export function ErrorBlock({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message =
    (error as { message?: string })?.message || 'Something went wrong loading this.'
  return (
    <div
      role="alert"
      style={{
        background: colors.errorDim,
        border: `1px solid ${colors.error}33`,
        borderRadius: radii.card,
        padding: '20px 18px',
        marginBottom: 14,
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 5 }}>Could not load</div>
      <div style={{ fontSize: 12, color: colors.textSecondary, lineHeight: 1.5, marginBottom: 12 }}>
        {message}
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          style={{
            background: 'transparent',
            border: `1px solid ${colors.surfaceBorder}`,
            color: colors.textPrimary,
            borderRadius: radii.button,
            padding: '8px 14px',
            fontSize: 12,
            cursor: 'pointer',
          }}
        >
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyBlock({ title, reason }: { title: string; reason: string }) {
  return (
    <Card>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 5 }}>{title}</div>
      <div style={{ fontSize: 12, color: colors.textSecondary, lineHeight: 1.5 }}>{reason}</div>
    </Card>
  )
}
