import { cleanup, render, screen, within } from '@testing-library/react'
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
    const navigation = screen.getByRole('navigation', { name: '教师工作区' })
    expect(within(navigation).getAllByRole('button').map((button) => button.textContent)).toEqual([
      '病例库',
      '问诊任务',
      '学员管理',
      '班级管理',
      '系统设置',
    ])
    expect(screen.getByRole('button', { name: '学员管理' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '问诊任务' })).toBeInTheDocument()

    rerender(<TeacherWorkspace />)
    expect(screen.queryByRole('button', { name: '学员管理' })).not.toBeInTheDocument()
    expect(within(navigation).getAllByRole('button').map((button) => button.textContent)).toEqual([
      '病例库',
      '问诊任务',
      '班级管理',
      '系统设置',
    ])
  })
})
