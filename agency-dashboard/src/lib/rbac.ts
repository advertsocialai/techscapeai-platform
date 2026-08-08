/**
 * Role helpers.
 *
 * READ THIS BEFORE USING ANY OF IT: a check in here is a UX affordance, not a
 * security boundary. The server re-reads the user's row on every request and
 * ignores the role claim in the token (`api/app/core/deps.py`), so hiding a
 * button prevents an accidental click — it does not prevent the action. Never
 * describe a screen as "restricted to admins" on the strength of a call to
 * `hasRole`; the restriction lives in the router dependency, and if that
 * dependency is missing the UI gate buys nothing.
 *
 * The stored role values are the backend's, which are NOT the names the
 * product spec uses. The spec's "admin tier" is stored as `manager`; `admin`
 * is the platform super-admin above it. Mapping the spec's vocabulary onto
 * these literals anywhere other than here has already caused one round of
 * confusion, so the translation is centralised.
 */
import type { BusinessUser } from '../types/auth'

/** Stored role values, ordered least- to most-privileged. */
export const ROLE_ORDER = ['viewer', 'user', 'manager', 'admin'] as const

export type Role = (typeof ROLE_ORDER)[number]

/**
 * Product vocabulary → stored value. Exported so screens can be written in the
 * language of the spec ("this is an admin screen") without hardcoding the fact
 * that admin-tier is persisted as `manager`.
 */
export const TIER: Record<'superAdmin' | 'admin' | 'agent' | 'viewer', Role> = {
  superAdmin: 'admin',
  admin: 'manager',
  agent: 'user',
  viewer: 'viewer',
}

function rank(role: string | null | undefined): number {
  // An unrecognised role ranks below viewer rather than throwing. A future
  // backend role we don't know about should degrade to "can see the least",
  // never to "can see everything" — fail closed.
  const i = ROLE_ORDER.indexOf(role as Role)
  return i === -1 ? -1 : i
}

/** True when `user` is at or above `minimum` in the role hierarchy. */
export function hasRole(
  user: Pick<BusinessUser, 'role'> | null | undefined,
  minimum: Role,
): boolean {
  if (!user) return false
  return rank(user.role) >= rank(minimum)
}

/** True when the user holds exactly one of the given roles. */
export function isRole(
  user: Pick<BusinessUser, 'role'> | null | undefined,
  ...roles: Role[]
): boolean {
  if (!user) return false
  return roles.includes(user.role as Role)
}

/** Display label for a stored role, in the product's vocabulary. */
export function roleLabel(role: string | null | undefined): string {
  switch (role) {
    case 'admin':
      return 'Super Admin'
    case 'manager':
      return 'Admin'
    case 'user':
      return 'Agent'
    case 'viewer':
      return 'Viewer'
    default:
      return 'Unknown'
  }
}

/**
 * Viewers are read-only across the whole product. Screens use this to disable
 * mutating controls rather than repeating the comparison inline — a viewer who
 * can click "Send WhatsApp" and receives a 403 has been told the wrong thing by
 * the UI twice over.
 */
export function isReadOnly(user: Pick<BusinessUser, 'role'> | null | undefined): boolean {
  return !hasRole(user, 'user')
}
