/**
 * Traveller — itinerary.
 *
 * Money is always amount + currency, never a bare number. This app is
 * multi-currency for international branches, and an unlabelled figure on a
 * customer's own booking is the worst place for that ambiguity.
 */
import { useQuery } from '@tanstack/react-query'

import { travellerApi } from '../../lib/travellerApi'
import { colors, radii } from '../../styles/tokens'
import { Card, EmptyBlock, ErrorBlock, Money, SkeletonBlock } from './ui'

const VISA_LABEL: Record<string, string> = {
  not_required: 'Not required',
  pending: 'Documents needed',
  submitted: 'Submitted',
  approved: 'Approved',
  rejected: 'Rejected',
}

export default function TripPage() {
  const tripQ = useQuery({ queryKey: ['traveller', 'trip'], queryFn: travellerApi.trip })

  if (tripQ.isLoading) return <SkeletonBlock rows={4} />

  // A 404 from GET /me/trip means "you have no active booking" — a real,
  // expected state, not a failure. It gets the empty state; anything else is a
  // genuine error and gets the retry block. Rendering a red error box at a
  // customer who simply has no upcoming trip would be alarming and wrong.
  if (tripQ.isError) {
    const status = (tripQ.error as { response?: { status?: number } })?.response?.status
    if (status === 404) {
      return (
        <EmptyBlock
          title="No active trip"
          reason="Once your agent confirms a booking it will appear here, with your itinerary and payments."
        />
      )
    }
    return <ErrorBlock error={tripQ.error} onRetry={() => tripQ.refetch()} />
  }

  // Was `return null` — a blank screen with no explanation, indistinguishable
  // from a broken page.
  if (!tripQ.data) {
    return (
      <EmptyBlock
        title="No active trip"
        reason="Once your agent confirms a booking it will appear here."
      />
    )
  }

  const trip = tripQ.data
  const outstanding = Number(trip.total_amount) - Number(trip.amount_paid)

  return (
    <>
      <Card>
        <div style={{ fontSize: 11, color: colors.textLabel, letterSpacing: 1, marginBottom: 6 }}>
          {trip.booking_ref}
        </div>
        <div style={{ fontSize: 26, fontWeight: 800, marginBottom: 4 }}>{trip.destination}</div>
        <div style={{ fontSize: 12, color: colors.textSecondary }}>
          {new Date(trip.start_date).toLocaleDateString()} –{' '}
          {new Date(trip.end_date).toLocaleDateString()} · {trip.pax} travellers
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
          <Chip tone="success">{trip.status}</Chip>
          <Chip tone={trip.visa_state === 'approved' ? 'success' : 'salmon'}>
            Visa: {VISA_LABEL[trip.visa_state] ?? trip.visa_state}
          </Chip>
        </div>
      </Card>

      <Card>
        <SectionTitle>Payment</SectionTitle>
        <Row label="Trip total" value={<Money amount={trip.total_amount} currency={trip.currency} />} />
        <Row label="Paid" value={<Money amount={trip.amount_paid} currency={trip.currency} />} />
        <Row
          label="Outstanding"
          value={<Money amount={String(outstanding)} currency={trip.currency} />}
          emphasis
        />
      </Card>

      <Card>
        <SectionTitle>Day by day</SectionTitle>
        <div style={{ display: 'grid', gap: 12 }}>
          {trip.itinerary.map((d) => (
            <div key={d.day} style={{ display: 'flex', gap: 12 }}>
              <div
                style={{
                  flex: 'none', width: 28, height: 28, borderRadius: 9,
                  background: colors.blueDim, border: `1px solid ${colors.blueBorder}`,
                  display: 'grid', placeItems: 'center',
                  fontSize: 11, fontWeight: 700, color: colors.blue,
                }}
              >
                {d.day}
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 2 }}>{d.title}</div>
                <div style={{ fontSize: 12, color: colors.textSecondary, lineHeight: 1.5 }}>
                  {d.detail}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <SectionTitle>Your agent</SectionTitle>
        <div style={{ fontSize: 13 }}>{trip.agent_name ?? 'Not assigned'}</div>
        <div style={{ fontSize: 12, color: colors.textSecondary }}>{trip.agency_name}</div>
      </Card>
    </>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>{children}</div>
  )
}

function Row({
  label,
  value,
  emphasis,
}: {
  label: string
  value: React.ReactNode
  emphasis?: boolean
}) {
  return (
    <div
      style={{
        display: 'flex', justifyContent: 'space-between', gap: 12,
        fontSize: 13, padding: '7px 0',
        fontWeight: emphasis ? 700 : 400,
        color: emphasis ? colors.textPrimary : undefined,
      }}
    >
      <span style={{ color: colors.textSecondary }}>{label}</span>
      <span>{value}</span>
    </div>
  )
}

function Chip({ children, tone }: { children: React.ReactNode; tone: 'success' | 'salmon' }) {
  const bg = tone === 'success' ? colors.successDim : colors.salmonDim
  const border = tone === 'success' ? colors.successBorder : colors.salmonBorder
  const fg = tone === 'success' ? colors.success : colors.salmon
  return (
    <span
      style={{
        background: bg, border: `1px solid ${border}`, color: fg,
        borderRadius: radii.chip, padding: '4px 11px', fontSize: 11, fontWeight: 600,
      }}
    >
      {children}
    </span>
  )
}
