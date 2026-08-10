/**
 * OtpPage — the six-box onboarding OTP screen.
 *
 * Pins the interaction contract: auto-send on mount, focus advancing as digits
 * are typed, paste-to-fill, and a verify button that stays disabled until all
 * six digits exist. lib/api is mocked at the module boundary; useNavigate is
 * mocked because the page renders outside any real route here.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import OtpPage from './OtpPage'
import { OnboardingProvider } from '../context/OnboardingContext'
import { authApi } from '../../../lib/api'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => mockNavigate,
}))

vi.mock('../../../lib/api', () => ({
  authApi: {
    sendOtp: vi.fn(),
    verifyOtp: vi.fn(),
  },
}))

const mockedApi = vi.mocked(authApi)

const EMAIL = 'new.user@example.com'

function renderPage() {
  return render(
    <OnboardingProvider>
      <OtpPage />
    </OnboardingProvider>,
  )
}

function boxes(): HTMLInputElement[] {
  return [1, 2, 3, 4, 5, 6].map(
    (n) => screen.getByLabelText(`OTP digit ${n} of 6`) as HTMLInputElement,
  )
}

function verifyButton(): HTMLButtonElement {
  return screen.getByRole('button', {
    name: /Verify & Continue/,
  }) as HTMLButtonElement
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  // The context email is empty on a hard refresh; the page falls back to this
  // key (see OtpPage.tsx) — the same fallback the send/verify pair relies on.
  localStorage.setItem('klara_otp_email', EMAIL)
  mockedApi.sendOtp.mockResolvedValue({} as never)
})

describe('rendering + auto-send', () => {
  it('renders six digit boxes with aria-labels and auto-sends the OTP', async () => {
    renderPage()
    expect(boxes()).toHaveLength(6)
    await waitFor(() => expect(mockedApi.sendOtp).toHaveBeenCalledWith(EMAIL))
  })

  it('with no email anywhere, says so instead of silently sending nothing', async () => {
    localStorage.clear()
    renderPage()
    expect(
      await screen.findByText(/We do not have your email address/),
    ).toBeTruthy()
    expect(mockedApi.sendOtp).not.toHaveBeenCalled()
  })

  it('a failed auto-send surfaces an error instead of six silent boxes', async () => {
    mockedApi.sendOtp.mockRejectedValueOnce(
      Object.assign(new Error('x'), {
        response: { status: 429, data: { detail: 'Too many OTP requests' } },
      }),
    )
    renderPage()
    expect(await screen.findByText('Too many OTP requests')).toBeTruthy()
  })
})

describe('digit entry', () => {
  it('typing a digit advances focus to the next box', async () => {
    const user = userEvent.setup()
    renderPage()
    const inputs = boxes()
    await user.type(inputs[0], '1')
    expect(document.activeElement).toBe(inputs[1])
    await user.type(inputs[1], '2')
    expect(document.activeElement).toBe(inputs[2])
  })

  it('backspace on an empty box moves back and clears the previous digit', async () => {
    const user = userEvent.setup()
    renderPage()
    const inputs = boxes()
    await user.type(inputs[0], '1')
    // focus is now on box 2, which is empty
    await user.keyboard('{Backspace}')
    expect(document.activeElement).toBe(inputs[0])
  })

  it('pasting 6 digits fills all boxes and enables verify', async () => {
    const user = userEvent.setup()
    renderPage()
    const inputs = boxes()
    expect(verifyButton().disabled).toBe(true)
    await user.click(inputs[0])
    await user.paste('123456')
    expect(verifyButton().disabled).toBe(false)
    // rendered digits live in the sibling spans, not the invisible inputs
    for (const d of ['1', '2', '3', '4', '5', '6']) {
      expect(screen.getByText(d)).toBeTruthy()
    }
  })

  it('verify stays disabled until every box is filled', async () => {
    const user = userEvent.setup()
    renderPage()
    const inputs = boxes()
    for (const [i, d] of ['9', '8', '7', '6', '5'].entries()) {
      await user.type(inputs[i], d)
      expect(verifyButton().disabled).toBe(true)
    }
    await user.type(inputs[5], '4')
    expect(verifyButton().disabled).toBe(false)
  })
})

describe('verify', () => {
  it('a full code verifies against the SAME email that was sent to, then navigates', async () => {
    mockedApi.verifyOtp.mockResolvedValueOnce({} as never)
    const user = userEvent.setup()
    renderPage()
    await user.click(boxes()[0])
    await user.paste('123456')
    await user.click(verifyButton())

    await waitFor(() =>
      expect(mockedApi.verifyOtp).toHaveBeenCalledWith(EMAIL, '123456'),
    )
    expect(mockNavigate).toHaveBeenCalledWith('/onboarding/terms')
  })

  it('a wrong code shows the server message, clears the boxes and does not navigate', async () => {
    mockedApi.verifyOtp.mockRejectedValueOnce(
      Object.assign(new Error('x'), {
        response: { status: 401, data: { detail: 'Invalid or expired OTP' } },
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await user.click(boxes()[0])
    await user.paste('000000')
    await user.click(verifyButton())

    expect(await screen.findByText('Invalid or expired OTP')).toBeTruthy()
    expect(mockNavigate).not.toHaveBeenCalled()
    expect(verifyButton().disabled).toBe(true) // boxes were reset
  })
})
