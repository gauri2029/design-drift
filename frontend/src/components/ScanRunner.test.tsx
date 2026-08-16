import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ScanRunner } from './ScanRunner'

describe('ScanRunner', () => {
  it('calls onRun when clicked', async () => {
    const onRun = vi.fn().mockResolvedValue(undefined)
    render(<ScanRunner onRun={onRun} running={false} />)

    fireEvent.click(screen.getByRole('button', { name: /run scan/i }))

    expect(onRun).toHaveBeenCalledTimes(1)
  })

  it('shows an error message when the scan fails', async () => {
    const onRun = vi.fn().mockRejectedValue(new Error('failed to load target_url'))
    render(<ScanRunner onRun={onRun} running={false} />)

    fireEvent.click(screen.getByRole('button', { name: /run scan/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('failed to load target_url')
  })

  it('disables the button while running', () => {
    render(<ScanRunner onRun={vi.fn()} running={true} />)

    expect(screen.getByRole('button', { name: /running scan/i })).toBeDisabled()
  })
})
