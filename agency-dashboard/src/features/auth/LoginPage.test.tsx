/**
 * LoginPage — the dashboard sign-in form.
 *
 * The auth module is mocked at the useAuth boundary (the real AuthProvider
 * fires a /auth/me probe on mount, which has no place in a unit suite);
 * routing is real, with a probe route standing in for the app shell.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LoginPage from './LoginPage'
import { useAuth } from '../../lib/auth'

vi.mock('../../lib/auth', () => ({
  useAuth: vi.fn(),
}))

const mockLogin = vi.fn()
const mockedUseAuth = vi.mocked(useAuth)

function renderPage(initialEntry: string | { pathname: string; state?: unknown } = '/login') {
  return render(
    <MemoryRouter initialEntries={[initialEntry as never]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>APP-SHELL-PROBE</div>} />
        <Route path="/live-calls" element={<div>LIVE-CALLS-PROBE</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedUseAuth.mockReturnValue({ login: mockLogin } as never)
})

describe('rendering', () => {
  it('renders email, password and submit', () => {
    renderPage()
    expect(screen.getByLabelText('Email')).toBeTruthy()
    expect(screen.getByLabelText('Password')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy()
  })
})

describe('validation', () => {
  it('an empty submit is blocked by field validation and never calls the API', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    const email = screen.getByLabelText('Email') as HTMLInputElement
    expect(email.validity.valueMissing).toBe(true)
    expect(mockLogin).not.toHaveBeenCalled()
  })
})

describe('submit', () => {
  it('successful login calls the api and navigates to the app shell', async () => {
    mockLogin.mockResolvedValueOnce(undefined)
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('Email'), 'ops@gogaga.example')
    await user.type(screen.getByLabelText('Password'), 'Str0ng!Passw0rd')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() =>
      expect(mockLogin).toHaveBeenCalledWith('ops@gogaga.example', 'Str0ng!Passw0rd'),
    )
    expect(await screen.findByText('APP-SHELL-PROBE')).toBeTruthy()
  })

  it('returns the operator to the page that bounced them here', async () => {
    mockLogin.mockResolvedValueOnce(undefined)
    const user = userEvent.setup()
    renderPage({ pathname: '/login', state: { from: '/live-calls' } })
    await user.type(screen.getByLabelText('Email'), 'ops@gogaga.example')
    await user.type(screen.getByLabelText('Password'), 'Str0ng!Passw0rd')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('LIVE-CALLS-PROBE')).toBeTruthy()
  })

  it('a 401 shows the server detail and stays on the page', async () => {
    mockLogin.mockRejectedValueOnce(
      Object.assign(new Error('x'), {
        response: { status: 401, data: { detail: 'Invalid credentials' } },
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('Email'), 'ops@gogaga.example')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Invalid credentials')).toBeTruthy()
    expect(screen.queryByText('APP-SHELL-PROBE')).toBeNull()
    // the button recovers so the operator can retry
    expect(
      (screen.getByRole('button', { name: 'Sign in' }) as HTMLButtonElement).disabled,
    ).toBe(false)
  })

  it('a 422 array detail renders as a message, not a crash', async () => {
    // Regression guard for the exact bug noted in LoginPage.tsx: `detail` is an
    // ARRAY on 422 and rendering it raw threw "Objects are not valid as a
    // React child".
    mockLogin.mockRejectedValueOnce(
      Object.assign(new Error('x'), {
        response: {
          status: 422,
          data: { detail: [{ loc: ['body', 'email'], msg: 'value is not a valid email address', type: 'value_error' }] },
        },
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('Email'), 'ops@gogaga.example')
    await user.type(screen.getByLabelText('Password'), 'whatever1')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText(/valid email address/)).toBeTruthy()
  })
})
