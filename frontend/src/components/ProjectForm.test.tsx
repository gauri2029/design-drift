import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ProjectForm } from './ProjectForm'

function fillForm() {
  fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: 'Marketing homepage' } })
  fireEvent.change(screen.getByLabelText(/figma file key/i), { target: { value: 'abc123' } })
  fireEvent.change(screen.getByLabelText(/figma node id/i), { target: { value: '1:23' } })
  fireEvent.change(screen.getByLabelText(/target app url/i), {
    target: { value: 'https://example.com' },
  })
}

describe('ProjectForm', () => {
  it('submits the entered values and resets the form', async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined)
    render(<ProjectForm onCreate={onCreate} submitting={false} />)

    fillForm()
    fireEvent.click(screen.getByRole('button', { name: /register project/i }))

    expect(onCreate).toHaveBeenCalledWith({
      name: 'Marketing homepage',
      figma_file_key: 'abc123',
      figma_node_id: '1:23',
      target_url: 'https://example.com',
    })
    expect(await screen.findByLabelText(/^name$/i)).toHaveValue('')
  })

  it('shows an error message when creation fails, without clearing the form', async () => {
    const onCreate = vi.fn().mockRejectedValue(new Error('Figma API request failed'))
    render(<ProjectForm onCreate={onCreate} submitting={false} />)

    fillForm()
    fireEvent.click(screen.getByRole('button', { name: /register project/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Figma API request failed')
    expect(screen.getByLabelText(/^name$/i)).toHaveValue('Marketing homepage')
  })

  it('disables the submit button while submitting', () => {
    render(<ProjectForm onCreate={vi.fn()} submitting={true} />)

    expect(screen.getByRole('button', { name: /fetching from figma/i })).toBeDisabled()
  })
})
