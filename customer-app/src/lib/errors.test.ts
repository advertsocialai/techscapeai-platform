/**
 * errorMessage() exists because a 422's `detail` is an ARRAY, and rendering it
 * as a React child white-screened the signup flow. These cases pin the envelope
 * handling — including the verbatim 422 captured from the live server.
 */
import { describe, expect, it } from 'vitest'
import { errorMessage } from './errors'

const respErr = (status: number, detail: unknown) => ({ response: { status, data: { detail } } })

describe('errorMessage', () => {
  it('handles the VERBATIM live 422 (array detail) without crashing', () => {
    const real422 = respErr(422, [
      {
        type: 'value_error',
        loc: ['body', 'user_password'],
        msg: 'Value error, Password must contain at least one uppercase letter, one special character',
        input: 'password123',
        ctx: { error: {} },
      },
    ])
    expect(errorMessage(real422)).toBe(
      'Password must contain at least one uppercase letter, one special character',
    )
  })

  it('passes a string detail straight through', () => {
    expect(errorMessage(respErr(409, 'User already exists'))).toBe('User already exists')
  })

  it('does NOT report a network failure as bad credentials', () => {
    expect(errorMessage({ message: 'Network Error' })).toBe(
      'Could not reach the server. Check your connection and try again.',
    )
  })

  it('maps bare statuses to actionable text', () => {
    expect(errorMessage(respErr(401, undefined))).toMatch(/session has expired/i)
    expect(errorMessage(respErr(429, undefined))).toMatch(/too many requests/i)
    expect(errorMessage(respErr(500, undefined))).toMatch(/server had a problem/i)
  })

  it('never returns the raw axios transport message', () => {
    expect(errorMessage({ message: 'Request failed with status code 500' })).toBe(
      'Could not reach the server. Check your connection and try again.',
    )
  })
})
