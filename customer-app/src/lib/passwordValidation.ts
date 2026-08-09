/**
 * Password rules — a mirror of the server's, deliberately.
 *
 * SOURCE OF TRUTH: `api/app/routers/techscape/auth.py` — `_PASSWORD_RULES`,
 * applied to `RegisterBusinessIn.user_password` and `PasswordResetIn.new_password`
 * via `_validate_password_strength`. If that tuple changes, change this list in
 * the same commit; there is no runtime link between them.
 *
 * This file exists because the two sides had drifted: the client checked length
 * only (`password.length < 8`) while the server demanded four character classes
 * as well. The user found out on the LAST screen of a four-screen signup, since
 * that is the first moment the password is transmitted — and the resulting 422
 * then crashed the screen rather than explaining itself (see lib/errors.ts).
 *
 * Kept identical to agency-dashboard/src/lib/passwordValidation.ts on purpose:
 * one product, one password policy, and two apps that must not disagree about
 * what a valid password is.
 */
export const PASSWORD_REQUIREMENTS: Array<{ label: string; test: (v: string) => boolean }> = [
  { label: 'At least 8 characters', test: (v) => v.length >= 8 },
  { label: 'One uppercase letter', test: (v) => /[A-Z]/.test(v) },
  { label: 'One lowercase letter', test: (v) => /[a-z]/.test(v) },
  { label: 'One number', test: (v) => /\d/.test(v) },
  { label: 'One special character', test: (v) => /[^A-Za-z0-9]/.test(v) },
]

export function passwordErrors(password: string): string[] {
  return PASSWORD_REQUIREMENTS.filter((r) => !r.test(password)).map((r) => r.label)
}

export function isPasswordValid(password: string): boolean {
  return passwordErrors(password).length === 0
}
