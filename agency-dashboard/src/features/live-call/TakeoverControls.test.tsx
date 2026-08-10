/**
 * TakeoverControls — the S11 takeover panel.
 *
 * The one rule the component exists to enforce is the one pinned hardest here:
 * the displayed state comes ONLY from the confirmed WS broadcast (the
 * `confirmed` prop). A successful POST must NOT flip the display — no
 * optimistic takeover UI, ever (see gogaga-frontend skill §6).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TakeoverControls from './TakeoverControls'
import { takeoverApi } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import type { TakeoverState } from '../../types/ws'

vi.mock('../../lib/api', () => ({
  takeoverApi: {
    monitor: vi.fn(),
    barge: vi.fn(),
    full: vi.fn(),
    release: vi.fn(),
  },
}))

vi.mock('../../lib/auth', () => ({
  useAuth: vi.fn(),
}))

const mockedApi = vi.mocked(takeoverApi)
const mockedUseAuth = vi.mocked(useAuth)

const CALL_ID = 'a0000000-0000-0000-0000-0000000000a1'

function renderPanel(props: {
  confirmed: TakeoverState | null
  isStale?: boolean
  callIsActive?: boolean
}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <TakeoverControls
        callId={CALL_ID}
        confirmed={props.confirmed}
        isStale={props.isStale ?? false}
        callIsActive={props.callIsActive ?? true}
      />
    </QueryClientProvider>,
  )
}

function btn(name: string | RegExp): HTMLButtonElement {
  return screen.getByRole('button', { name }) as HTMLButtonElement
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedUseAuth.mockReturnValue({
    me: { user: { role: 'manager' } },
  } as never)
})

describe('unknown state (no WS broadcast yet)', () => {
  it('says the state is unknown and disables every action', () => {
    renderPanel({ confirmed: null })
    expect(screen.getByText('state unknown')).toBeTruthy()
    expect(screen.getByText(/No takeover broadcast received yet/)).toBeTruthy()
    for (const name of ['Monitor', 'Coach', 'Take over', 'Release to AI']) {
      expect(btn(name).disabled, name).toBe(true)
    }
  })
})

describe('button legality tracks the confirmed state', () => {
  it('from "ai": escalations enabled, Release disabled', () => {
    renderPanel({ confirmed: 'ai' })
    expect(screen.getByText('AI handling')).toBeTruthy()
    expect(btn('Monitor').disabled).toBe(false)
    expect(btn('Coach').disabled).toBe(false)
    expect(btn('Take over').disabled).toBe(false)
    expect(btn('Release to AI').disabled).toBe(true)
  })

  it('from "human": only Release is enabled', () => {
    renderPanel({ confirmed: 'human' })
    expect(screen.getByText('You have the call')).toBeTruthy()
    expect(btn('Monitor').disabled).toBe(true)
    expect(btn('Coach').disabled).toBe(true)
    expect(btn('Take over').disabled).toBe(true)
    expect(btn('Release to AI').disabled).toBe(false)
  })

  it('an inactive call disables everything regardless of state', () => {
    renderPanel({ confirmed: 'ai', callIsActive: false })
    for (const name of ['Monitor', 'Coach', 'Take over', 'Release to AI']) {
      expect(btn(name).disabled, name).toBe(true)
    }
  })

  it('a read-only role disables everything and says why', () => {
    mockedUseAuth.mockReturnValue({ me: { user: { role: 'viewer' } } } as never)
    renderPanel({ confirmed: 'ai' })
    expect(screen.getByText(/read-only/)).toBeTruthy()
    for (const name of ['Monitor', 'Coach', 'Take over', 'Release to AI']) {
      expect(btn(name).disabled, name).toBe(true)
    }
  })

  it('a stale feed shows the out-of-date warning', () => {
    renderPanel({ confirmed: 'ai', isStale: true })
    expect(screen.getByText(/state shown may be out of date/)).toBeTruthy()
  })
})

describe('low-consequence action: Monitor', () => {
  it('fires immediately — no confirmation dialog', async () => {
    mockedApi.monitor.mockResolvedValueOnce({} as never)
    const user = userEvent.setup()
    renderPanel({ confirmed: 'ai' })
    await user.click(btn('Monitor'))
    await waitFor(() => expect(mockedApi.monitor).toHaveBeenCalledWith(CALL_ID))
  })

  it('NEVER flips the display optimistically — state stays with the WS prop', async () => {
    let resolve!: (v: unknown) => void
    mockedApi.monitor.mockReturnValueOnce(
      new Promise((r) => { resolve = r }) as never,
    )
    const user = userEvent.setup()
    renderPanel({ confirmed: 'ai' })
    await user.click(btn('Monitor'))

    // in flight: explicitly pending, neither old nor guessed-new state
    expect(screen.getByText('requesting…')).toBeTruthy()

    resolve({})
    // settled: the display returns to the CONFIRMED state ("ai"), not to
    // "monitoring" — only the takeover_state broadcast may change it.
    expect(await screen.findByText('AI handling')).toBeTruthy()
    expect(screen.queryByText('You are monitoring')).toBeNull()
  })

  it('a 409 from the state machine is surfaced as an alert', async () => {
    mockedApi.monitor.mockRejectedValueOnce(
      Object.assign(new Error('x'), {
        response: { status: 409, data: { detail: 'Illegal transition human -> monitoring' } },
      }),
    )
    const user = userEvent.setup()
    renderPanel({ confirmed: 'ai' })
    await user.click(btn('Monitor'))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('Illegal transition')
  })
})

describe('high-consequence action: Take over', () => {
  it('asks for confirmation first and does not call the API', async () => {
    const user = userEvent.setup()
    renderPanel({ confirmed: 'ai' })
    await user.click(btn('Take over'))
    expect(screen.getByRole('alertdialog')).toBeTruthy()
    expect(mockedApi.full).not.toHaveBeenCalled()
  })

  it('confirming fires the takeover', async () => {
    mockedApi.full.mockResolvedValueOnce({} as never)
    const user = userEvent.setup()
    renderPanel({ confirmed: 'ai' })
    await user.click(btn('Take over'))
    await user.click(btn(/Yes, take over/))
    await waitFor(() => expect(mockedApi.full).toHaveBeenCalledWith(CALL_ID))
  })

  it('cancelling closes the dialog and fires nothing', async () => {
    const user = userEvent.setup()
    renderPanel({ confirmed: 'ai' })
    await user.click(btn('Take over'))
    await user.click(btn('Cancel'))
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(mockedApi.full).not.toHaveBeenCalled()
  })

  it('the other three actions deliberately skip confirmation', () => {
    // pinned so nobody "helpfully" adds dialogs everywhere — confirmation
    // fatigue is why only the human handoff gets one.
    renderPanel({ confirmed: 'monitoring' })
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })
})
