/**
 * Traveller — payments.
 *
 * 💰 A `stub://` URL is rendered as inert text, never as a link. That mirrors
 * what the backend returns without Razorpay credentials, and it is the whole
 * point of keeping the stub URL in the fixture: a customer who clicks a dead
 * "Pay now" button and lands nowhere will assume the booking is broken.
 */
import { useQuery } from '@tanstack/react-query'

import { travellerApi } from '../../lib/travellerApi'
import { colors, radii } from '../../styles/tokens'
import { Card, EmptyBlock, ErrorBlock, Money, SkeletonBlock } from './ui'

const STATUS_TONE: Record<string, { bg: string; border: string; fg: string }> = {
  paid: { bg: colors.successDim, border: colors.successBorder, fg: colors.success },
  sent: { bg: colors.blueDim, border: colors.blueBorder, fg: colors.blue },
  viewed: { bg: colors.salmonDim, border: colors.salmonBorder, fg: colors.salmon },
  created: { bg: colors.blueDim, border: colors.blueBorder, fg: colors.blue },
  expired: { bg: colors.errorDim, border: `${colors.error}33`, fg: colors.error },
}

export default function PaymentsPage() {
  const paymentsQ = useQuery({
    queryKey: ['traveller', 'payments'],
    queryFn: travellerApi.payments,
  })

  if (paymentsQ.isLoading) return <SkeletonBlock rows={3} />
  if (paymentsQ.isError) {
    return <ErrorBlock error={paymentsQ.error} onRetry={() => paymentsQ.refetch()} />
  }

  const payments = paymentsQ.data ?? []
  if (payments.length === 0) {
    return (
      <EmptyBlock
        title="No payments yet"
        reason="Your agent will send a payment link when your booking is ready."
      />
    )
  }

  return (
    <>
      {payments.map((p) => {
        const tone = STATUS_TONE[p.status] ?? STATUS_TONE.created
        const payable = p.status !== 'paid' && p.status !== 'expired'
        const isStubUrl = !!p.pay_url && p.pay_url.startsWith('stub://')

        return (
          <Card key={p.id}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{p.description}</div>
              <span
                style={{
                  background: tone.bg, border: `1px solid ${tone.border}`, color: tone.fg,
                  borderRadius: radii.chip, padding: '3px 10px', fontSize: 10,
                  fontWeight: 700, height: 'fit-content', whiteSpace: 'nowrap',
                }}
              >
                {p.status}
              </span>
            </div>

            <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 6 }}>
              <Money amount={p.amount} currency={p.currency} />
            </div>

            {p.due_at && (
              <div style={{ fontSize: 11, color: colors.textSecondary, marginBottom: 12 }}>
                Due {new Date(p.due_at).toLocaleDateString()}
              </div>
            )}

            {payable && (
              isStubUrl || !p.pay_url ? (
                // Inert on purpose. A disabled control with a stated reason is
                // far better than a button that goes nowhere.
                <div
                  style={{
                    background: colors.inputBg,
                    border: `1px dashed ${colors.surfaceBorder}`,
                    borderRadius: radii.button,
                    padding: '11px 14px',
                    fontSize: 11,
                    color: colors.textSecondary,
                    lineHeight: 1.5,
                  }}
                >
                  Payment link not active — the gateway is running in stub mode, so this link
                  cannot take a payment.
                </div>
              ) : (
                <a
                  href={p.pay_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: 'block', textAlign: 'center', textDecoration: 'none',
                    background: colors.blueGrad, color: '#fff',
                    borderRadius: radii.button, padding: '13px 0',
                    fontSize: 14, fontWeight: 700,
                  }}
                >
                  Pay now
                </a>
              )
            )}
          </Card>
        )
      })}
    </>
  )
}
