import { Navigate, useLocation } from 'react-router-dom'
import { isTravellerAuthenticated } from '../../lib/travellerApi'

/**
 * Guards the traveller surface.
 *
 * TIMING IS THE WHOLE POINT. `/trip` deliberately had NO guard while
 * `travellerApi` returned fixtures — a guard checking an AGENCY token would
 * have been the wrong check dressed up as security, and there was nothing to
 * protect because a fixture cannot leak. The audit's condition was "add this at
 * the same moment the stub flag flips, not before". The flag is now false and
 * these screens render a real customer's booking, so the guard lands with it.
 *
 * As always, this is the FIRST line of defence and never the guarantee: the
 * backend requires a traveller token on every /me endpoint and scopes each
 * query by customer_id AND business_id from that token. Remove this component
 * and no data leaks — you just get 401s and ugly screens. That is the correct
 * ordering of responsibility.
 */
export default function RequireTraveller({ children }: { children: React.ReactNode }) {
  const location = useLocation()

  if (!isTravellerAuthenticated()) {
    // /trip/login, NOT /onboarding/login: that form asks for a password, and a
    // traveller has none. Sending them there was a dead end — a guard with
    // nowhere to send people is not security, it is a broken door.
    // `state.from` returns them to the page they actually wanted.
    return <Navigate to="/trip/login" replace state={{ from: location.pathname }} />
  }

  return <>{children}</>
}
