/**
 * TravellerLoginPage — the OTP sign-in for /trip.
 *
 * The contract pinned here mirrors the backend's enumeration stance:
 * request-otp ALWAYS advances to the code step (the server 202s whether or not
 * the email is on a booking), and a wrong code shows one generic message. The
 * API module is mocked at the boundary; routing is real (MemoryRouter with a
 * probe route standing in for /trip).
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TravellerLoginPage from './TravellerLoginPage'
import { travellerApi } from '../../lib/travellerApi'

vi.mock('../../lib/travellerApi', () => ({
  travellerApi: {
    requestOtp: vi.fn(),
    verifyOtp: vi.fn(),
  },
}))

const mockedApi = vi.mocked(travellerApi)

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/trip/login']}>
      <Routes>
        <Route path="/trip/login" element={<TravellerLoginPage />} />
        <Route path="/trip" element={<div>TRIP-HOME-PROBE</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

function http401(detail: string) {
  return Object.assign(new Error(detail), {
    response: { status: 401, data: { detail } },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('email step', () => {
  it('renders the email step first', () => {
    renderPage()
    expect(screen.getByText('View your trip')).toBeTruthy()
    expect(screen.getByLabelText('Email address on your booking')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Send me a code' })).toBeTruthy()
  })

  it('empty email shows an inline error and never calls the API', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Send me a code' }))
    expect(screen.getByText('Enter the email address on your booking')).toBeTruthy()
    expect(mockedApi.requestOtp).not.toHaveBeenCalled()
  })

  it('successful requestOtp advances to the code step', async () => {
    mockedApi.requestOtp.mockResolvedValueOnce({})
    const user = userEvent.setup()
    renderPage()
    await user.type(
      screen.getByLabelText('Email address on your booking'),
      'guest@example.com',
    )
    await user.click(screen.getByRole('button', { name: 'Send me a code' }))

    expect(mockedApi.requestOtp).toHaveBeenCalledWith('guest@example.com')
    expect(await screen.findByText('Check your email')).toBeTruthy()
    // Enumeration stance: the copy hedges, it does not confirm the address.
    expect(
      screen.getByText(/If guest@example.com is on a booking/),
    ).toBeTruthy()
  })

  it('Enter in the email field submits (same path as the button)', async () => {
    mockedApi.requestOtp.mockResolvedValueOnce({})
    const user = userEvent.setup()
    renderPage()
    await user.type(
      screen.getByLabelText('Email address on your booking'),
      'guest@example.com{Enter}',
    )
    expect(mockedApi.requestOtp).toHaveBeenCalledWith('guest@example.com')
    expect(await screen.findByText('Check your email')).toBeTruthy()
  })
})

describe('code step', () => {
  async function toCodeStep(user: ReturnType<typeof userEvent.setup>) {
    mockedApi.requestOtp.mockResolvedValueOnce({})
    await user.type(
      screen.getByLabelText('Email address on your booking'),
      'guest@example.com',
    )
    await user.click(screen.getByRole('button', { name: 'Send me a code' }))
    await screen.findByText('Check your email')
  }

  it('a wrong code surfaces the server message and stays on the code step', async () => {
    const user = userEvent.setup()
    renderPage()
    await toCodeStep(user)

    mockedApi.verifyOtp.mockRejectedValueOnce(http401('Invalid or expired code'))
    await user.type(screen.getByLabelText('6-digit code from your email'), '000000')
    await user.click(screen.getByRole('button', { name: 'View my trip →' }))

    expect(await screen.findByText('Invalid or expired code')).toBeTruthy()
    expect(screen.queryByText('TRIP-HOME-PROBE')).toBeNull()
  })

  it('a short code is rejected locally without calling the API', async () => {
    const user = userEvent.setup()
    renderPage()
    await toCodeStep(user)

    await user.type(screen.getByLabelText('6-digit code from your email'), '12')
    await user.click(screen.getByRole('button', { name: 'View my trip →' }))
    expect(screen.getByText('Enter the code from your email')).toBeTruthy()
    expect(mockedApi.verifyOtp).not.toHaveBeenCalled()
  })

  it('a correct code verifies and navigates to /trip', async () => {
    const user = userEvent.setup()
    renderPage()
    await toCodeStep(user)

    mockedApi.verifyOtp.mockResolvedValueOnce({ access_token: 't' })
    await user.type(screen.getByLabelText('6-digit code from your email'), '123456')
    await user.click(screen.getByRole('button', { name: 'View my trip →' }))

    await waitFor(() =>
      expect(mockedApi.verifyOtp).toHaveBeenCalledWith('guest@example.com', '123456'),
    )
    expect(await screen.findByText('TRIP-HOME-PROBE')).toBeTruthy()
  })

  it('Enter in the code field triggers verify', async () => {
    const user = userEvent.setup()
    renderPage()
    await toCodeStep(user)

    mockedApi.verifyOtp.mockResolvedValueOnce({ access_token: 't' })
    await user.type(
      screen.getByLabelText('6-digit code from your email'),
      '123456{Enter}',
    )
    await waitFor(() =>
      expect(mockedApi.verifyOtp).toHaveBeenCalledWith('guest@example.com', '123456'),
    )
  })

  it('the code input strips non-digits and caps at 6', async () => {
    const user = userEvent.setup()
    renderPage()
    await toCodeStep(user)

    const input = screen.getByLabelText(
      '6-digit code from your email',
    ) as HTMLInputElement
    await user.type(input, '12ab34-56 789')
    expect(input.value).toBe('123456')
  })
})
