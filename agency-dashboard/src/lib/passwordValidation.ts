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
