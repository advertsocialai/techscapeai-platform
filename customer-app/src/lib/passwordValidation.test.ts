/**
 * These rules MIRROR the server's _PASSWORD_RULES (api/app/routers/techscape/
 * auth.py). There is no runtime link between the two — this suite is the link.
 * If the server tuple changes and this file doesn't, these cases are where the
 * drift shows up first, instead of on screen 4 of a customer's signup.
 */
import { describe, expect, it } from 'vitest'
import { isPasswordValid, passwordErrors, PASSWORD_REQUIREMENTS } from './passwordValidation'

describe('password rules mirror the server', () => {
  it('has exactly the five server rules', () => {
    expect(PASSWORD_REQUIREMENTS).toHaveLength(5)
  })

  it('rejects the exact password the live 422 was captured with', () => {
    // password123 → server said: "one uppercase letter, one special character"
    expect(isPasswordValid('password123')).toBe(false)
    expect(passwordErrors('password123')).toEqual([
      'One uppercase letter',
      'One special character',
    ])
  })

  it('accepts a fully compliant password', () => {
    expect(isPasswordValid('Passw0rd!')).toBe(true)
    expect(passwordErrors('Passw0rd!')).toEqual([])
  })

  it.each([
    ['short', 'Ab1!'],
    ['no uppercase', 'passw0rd!'],
    ['no lowercase', 'PASSW0RD!'],
    ['no digit', 'Password!'],
    ['no symbol', 'Passw0rdX'],
  ])('rejects %s', (_label, pw) => {
    expect(isPasswordValid(pw)).toBe(false)
  })
})
