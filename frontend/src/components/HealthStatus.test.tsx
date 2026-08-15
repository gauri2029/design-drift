import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HealthStatus } from './HealthStatus'

describe('HealthStatus', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows a connected message when the backend responds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok', service: 'design-drift-backend' }),
      }),
    )

    render(<HealthStatus />)

    expect(await screen.findByText(/connected to design-drift-backend/i)).toBeInTheDocument()
  })

  it('shows an error message when the backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))

    render(<HealthStatus />)

    expect(await screen.findByText(/backend unreachable/i)).toBeInTheDocument()
  })
})
