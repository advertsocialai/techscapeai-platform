/**
 * Currency rendering.
 *
 * The one rule: NEVER render a bare amount. The platform is multi-branch and
 * multi-currency (INR, plus USD/CAD for international branches), so "45,000"
 * on a screen is genuinely ambiguous in a way that costs money. Every export
 * here requires a currency alongside the amount, which is why there is no
 * `formatAmount(n)` — the missing function is the point.
 *
 * The UI must also never convert. The backend converts historical rows using
 * the FX snapshot in effect at each transaction's own timestamp (migration
 * 0015), so a report re-run days later is byte-identical. Re-deriving a total
 * client-side against a live rate would quietly break that guarantee.
 */

/** Amounts arrive from the API as strings (NUMERIC) or numbers depending on route. */
export type Amount = number | string | null | undefined

function toNumber(value: Amount): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : null
}

/**
 * Format an amount with its currency. `currency` is required and not defaulted:
 * a default would reintroduce exactly the ambiguity this module exists to stop.
 */
export function formatMoney(
  value: Amount,
  currency: string | null | undefined,
  opts: { maximumFractionDigits?: number } = {},
): string {
  const n = toNumber(value)
  const code = (currency || '').toUpperCase()

  // No currency is a data problem, not a formatting problem. Show the number
  // flagged rather than silently implying INR.
  if (!code) return n === null ? '—' : `${n.toLocaleString('en-IN')} (currency unknown)`
  if (n === null) return '—'

  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: code,
      maximumFractionDigits: opts.maximumFractionDigits ?? 0,
    }).format(n)
  } catch {
    // Unknown ISO code — still render the code so the figure stays unambiguous.
    return `${n.toLocaleString('en-IN')} ${code}`
  }
}

/**
 * Render a server-side rollup. `unconvertible` is the count of rows the backend
 * could not convert into the report currency.
 *
 * A rollup that silently omits rows is worse than one that is obviously
 * incomplete: the first is trusted and wrong, the second prompts a question. So
 * an incomplete total is always labelled, never rounded off into the number.
 */
export function formatRollup(rollup: {
  total: Amount
  currency: string | null | undefined
  unconvertible?: number | null
}): { text: string; incomplete: boolean; note: string | null } {
  const skipped = rollup.unconvertible ?? 0
  const text = formatMoney(rollup.total, rollup.currency)
  if (skipped > 0) {
    return {
      text,
      incomplete: true,
      note: `${skipped} row${skipped === 1 ? '' : 's'} could not be converted and are excluded from this total`,
    }
  }
  return { text, incomplete: false, note: null }
}
