/**
 * Turning a thrown value into something worth showing a user.
 *
 * Lives in `lib/` rather than beside `ErrorState` because a plain function
 * exported from a component module breaks React Fast Refresh — and because
 * non-visual code paths (mutation handlers, toasts, logging) want it too.
 */

/**
 * Prefers the backend's `detail`, which is the human-written half of a FastAPI
 * `HTTPException` and is almost always more useful than the status code. Falls
 * back to a status-specific line, then the transport error.
 *
 * Note what is NOT here: the raw axios message ("Request failed with status
 * code 500"). It describes the transport to a developer and tells a user
 * nothing they can act on.
 */
export function errorMessage(err: unknown): string {
  const res = (err as { response?: { status?: number; data?: { detail?: unknown } } })?.response
  const detail = res?.data?.detail

  if (typeof detail === 'string' && detail) return detail

  // FastAPI validation errors arrive as a list of {loc, msg, type}.
  if (Array.isArray(detail)) {
    const first = detail.find(
      (d): d is { msg: string } => !!d && typeof (d as { msg?: unknown }).msg === 'string',
    )
    if (first) return first.msg
  }

  const status = res?.status
  if (status === 401) return 'Your session has expired. Sign in again.'
  if (status === 403) return 'You do not have access to this.'
  if (status === 404) return 'Not found.'
  if (status === 409) return 'That conflicts with something that already exists.'
  if (status === 429) return 'Too many requests. Wait a moment and try again.'
  if (status && status >= 500) return 'The server had a problem. This is usually temporary.'

  const message = (err as { message?: string })?.message
  if (message && !/^Request failed with status code/.test(message)) return message

  return 'Something went wrong.'
}
