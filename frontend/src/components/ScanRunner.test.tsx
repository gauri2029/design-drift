import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ScanRunner } from './ScanRunner'

describe('ScanRunner', () => {
  it('calls onRun with match_figma by default', async () => {
    const onRun = vi.fn().mockResolvedValue(undefined)
    render(<ScanRunner onRun={onRun} onRunAllBreakpoints={vi.fn()} running={false} />)

    fireEvent.click(screen.getByRole('button', { name: /^run scan$/i }))

    expect(onRun).toHaveBeenCalledWith('match_figma')
  })

  it('calls onRun with the selected breakpoint', async () => {
    const onRun = vi.fn().mockResolvedValue(undefined)
    render(<ScanRunner onRun={onRun} onRunAllBreakpoints={vi.fn()} running={false} />)

    fireEvent.change(screen.getByLabelText(/scan mode/i), { target: { value: 'mobile' } })
    fireEvent.click(screen.getByRole('button', { name: /^run scan$/i }))

    expect(onRun).toHaveBeenCalledWith('mobile')
  })

  it('calls onRunAllBreakpoints when that button is clicked', async () => {
    const onRunAllBreakpoints = vi.fn().mockResolvedValue(undefined)
    render(<ScanRunner onRun={vi.fn()} onRunAllBreakpoints={onRunAllBreakpoints} running={false} />)

    fireEvent.click(screen.getByRole('button', { name: /run all breakpoints/i }))

    expect(onRunAllBreakpoints).toHaveBeenCalledTimes(1)
  })

  it('shows an error message when the scan fails', async () => {
    const onRun = vi.fn().mockRejectedValue(new Error('failed to load target_url'))
    render(<ScanRunner onRun={onRun} onRunAllBreakpoints={vi.fn()} running={false} />)

    fireEvent.click(screen.getByRole('button', { name: /^run scan$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('failed to load target_url')
  })

  it('disables both buttons while running', () => {
    render(<ScanRunner onRun={vi.fn()} onRunAllBreakpoints={vi.fn()} running={true} />)

    expect(screen.getByRole('button', { name: /running scan/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /run all breakpoints/i })).toBeDisabled()
  })
})
