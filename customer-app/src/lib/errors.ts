/**
 * Turning a thrown value into something worth showing a user.
 *
 * WHY THIS EXISTS — it fixes a crash, not just a wording problem.
 *
 * FastAPI's `detail` is NOT always a string. For an `HTTPException` it is
 * (`{"detail": "User already exists"}`), but for a 422 validation failure it is
 * a LIST of objects:
 *
 *   {"detail": [{"type": "value_error", "loc": ["body", "user_password"],
 *                "msg": "Value error, Password must contain at least one
 *                        uppercase letter, one special character",
 *                "input": "…", "ctx": {…}}]}
 *
 * Every call site here used to do:
 *
 *   const detail = (err as { response?: { data?: { detail?: string } } })…
 *   setError(detail || 'Something went wrong.')
 *
 * The cast asserts `string`; the array is truthy, so it sailed through and was
 * rendered as a React child — which throws "Objects are not valid as a React
 * child" and takes the screen down. A weak password on the signup form produced
 * a white screen instead of the message explaining exactly what was wrong.
 *
 * Ported from agency-dashboard/src/lib/errors.ts so both apps report identical
 * text for identical backend failures.
 */
export function errorMessage(err: unknown): string {
  const res = (err as { response?: { status?: number; data?: { detail?: unknown } } })?.response
  const detail = res?.data?.detail

  if (typeof detail === 'string' && detail) return detail

  // FastAPI validation errors: a list of {loc, msg, type}. `msg` is prefixed
  // with "Value error, " by Pydantic for custom validators — strip it, since
  // it names an implementation detail the customer cannot act on.
  if (Array.isArray(detail)) {
    const first = detail.find(
      (d): d is { msg: string } => !!d && typeof (d as { msg?: unknown }).msg === 'string',
    )
    if (first) return first.msg.replace(/^Value error,\s*/i, '')
  }

  const status = res?.status
  if (status === 401) return 'Your session has expired. Sign in again.'
  if (status === 403) return 'You do not have access to this.'
  if (status === 404) return 'Not found.'
  if (status === 409) return 'That conflicts with something that already exists.'
  if (status === 429) return 'Too many requests. Wait a moment and try again.'
  if (status && status >= 500) return 'The server had a problem. This is usually temporary.'

  // No response at all — the request never reached the server.
  if (!res) return 'Could not reach the server. Check your connection and try again.'

  const message = (err as { message?: string })?.message
  if (message && !/^Request failed with status code/.test(message)) return message

  return 'Something went wrong.'
}
