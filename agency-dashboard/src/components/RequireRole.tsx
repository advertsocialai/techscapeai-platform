/**
 * Route- and section-level role gating.
 *
 * This hides things. It does not protect them — see the warning at the top of
 * `lib/rbac.ts`. Use it so a viewer isn't shown a Tenant Management link that
 * would 403 on click, not as the reason a screen is safe.
 */
import type { ReactNode } from 'react'
import { useAuth } from '../lib/auth'
import { hasRole, type Role } from '../lib/rbac'

/**
 * Renders `children` only when the signed-in user is at or above `minimum`.
 *
 * `fallback` defaults to nothing, which is right for nav links and buttons. For
 * a whole route, pass an explicit fallback: a user who follows a bookmark to a
 * page above their level should be told they lack access, not shown a blank
 * screen they'll read as a broken app.
 */
export default function RequireRole({
  minimum,
  children,
  fallback = null,
}: {
  minimum: Role
  children: ReactNode
  fallback?: ReactNode
}) {
  const { me } = useAuth()
  if (!hasRole(me?.user, minimum)) return <>{fallback}</>
  return <>{children}</>
}

/** Full-page fallback for a route the user cannot open. */
export function NoAccess({ what = 'this page' }: { what?: string }) {
  return (
    <div className="state-block" role="alert">
      <p className="state-title">You don't have access to {what}</p>
      <p className="state-reason">
        Ask an admin on your team if you need it. Your current role is set on your user account.
      </p>
    </div>
  )
}
