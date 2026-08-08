import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TeacherWorkspace } from './TeacherWorkspace'

describe('TeacherWorkspace', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows student management only to administrators', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    )

    const { rerender } = render(<TeacherWorkspace isAdministrator />)
    expect(screen.getByRole('button', { name: '学员管理' })).toBeInTheDocument()

    rerender(<TeacherWorkspace />)
    expect(screen.queryByRole('button', { name: '学员管理' })).not.toBeInTheDocument()
  })
})
