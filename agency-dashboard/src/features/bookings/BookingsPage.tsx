import { useQuery } from '@tanstack/react-query'
import { bookingsApi } from '../../lib/api'

function formatInr(n: number) {
  return `₹${n.toLocaleString('en-IN')}`
}

const STATUS_BADGE: Record<string, string> = {
  confirmed: 'blue',
  in_progress: 'amber',
  completed: 'green',
  cancelled: 'white',
}

export default function BookingsPage() {
  const { data: bookings, isLoading, isError } = useQuery({ queryKey: ['bookings'], queryFn: () => bookingsApi.list() })

  const totalRevenue = (bookings ?? []).reduce((sum, b) => sum + (b.grand_total_inr || 0), 0)

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Bookings</div>
          <div className="page-sub">{bookings?.length ?? 0} bookings · {formatInr(totalRevenue)} total</div>
        </div>
      </div>
      <div className="content">
        {isLoading && <div className="loading-block">Loading…</div>}
        {isError && <div className="error-banner">Could not load bookings.</div>}
        {!isLoading && !isError && (
          <div className="card">
            {(bookings ?? []).length === 0 ? (
              <div className="empty-state">
                <div className="icon">📋</div>
                <div>No bookings yet.</div>
              </div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Booking Ref</th>
                    <th>Destination</th>
                    <th>Trip</th>
                    <th>Dates</th>
                    <th>Pax</th>
                    <th>Total</th>
                    <th>Balance</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(bookings ?? []).map((b) => (
                    <tr key={b.id}>
                      <td>{b.booking_ref}</td>
                      <td>{b.destination || '—'}</td>
                      <td>{b.trip_type || '—'}</td>
                      <td>{b.departure_date} → {b.return_date}</td>
                      <td>{b.pax_count}</td>
                      <td style={{ color: 'var(--amber)', fontWeight: 700 }}>{formatInr(b.grand_total_inr)}</td>
                      <td>{formatInr(b.balance_inr)}</td>
                      <td><span className={`badge ${STATUS_BADGE[b.status] || 'white'}`}>{b.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </>
  )
}
