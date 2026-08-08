import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ClassManagement } from './ClassManagement'

const classRecord = {
  id: 'class-1',
  code: 'CLASS-INTERNAL-A',
  name: 'A 班',
  created_by_name: '教师甲',
  is_active: true,
  student_count: 1,
  students: [],
  created_at: '2026-08-04T00:00:00Z',
}

describe('ClassManagement', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows a create button by default and creates a class from its name only', async () => {
    let classes = [classRecord]
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"teacher-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/teacher/teaching/classes/') && init?.method === 'POST') {
        expect(JSON.parse(String(init.body))).toEqual({ name: 'B 班' })
        const created = {
          ...classRecord,
          id: 'class-2',
          code: 'CLASS-INTERNAL-B',
          name: 'B 班',
          student_count: 0,
        }
        classes = [...classes, created]
        return Promise.resolve(new Response(JSON.stringify(created), { status: 201 }))
      }
      if (url.endsWith('/teacher/teaching/classes/')) {
        return Promise.resolve(new Response(JSON.stringify(classes), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<ClassManagement />)
    await waitFor(() => expect(screen.getByRole('button', { name: '创建班级' })).toBeEnabled())
    expect(screen.queryByRole('dialog', { name: '创建班级' })).not.toBeInTheDocument()
    expect(screen.queryByText('CLASS-INTERNAL-A')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '管理学生' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '创建班级' }))
    expect(screen.getByRole('dialog', { name: '创建班级' })).toBeInTheDocument()
    expect(screen.queryByLabelText('班级编号')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('班级名称'), { target: { value: 'B 班' } })
    fireEvent.click(screen.getByRole('button', { name: '确认创建' }))

    expect(await screen.findByRole('heading', { name: 'B 班' })).toBeInTheDocument()
    expect(screen.getByText('班级已创建，学生注册时可以选择该班级。')).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: '创建班级' })).not.toBeInTheDocument()
  })

  it('deletes and restores classes while retaining historical data', async () => {
    const deletedClass = {
      ...classRecord,
      id: 'class-2',
      name: 'B 班',
      is_active: false,
      student_count: 0,
    }
    let classes = [classRecord, deletedClass]
    vi.spyOn(globalThis, 'confirm').mockReturnValue(true)
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"teacher-csrf"}', { status: 200 }))
      }
      if (url.includes('/teacher/teaching/classes/') && init?.method === 'PATCH') {
        const classId = url.includes('class-1') ? 'class-1' : 'class-2'
        const { is_active: isActive } = JSON.parse(String(init.body)) as { is_active: boolean }
        classes = classes.map((item) => item.id === classId
          ? { ...item, is_active: isActive }
          : item)
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      if (url.endsWith('/teacher/teaching/classes/')) {
        return Promise.resolve(new Response(JSON.stringify(classes), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<ClassManagement />)
    await waitFor(() => expect(screen.getByText('已删除')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '删除班级' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '恢复班级' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '删除班级' }))
    expect(await screen.findByText('班级“A 班”已删除，历史记录保持不变。')).toBeInTheDocument()
    expect(screen.getAllByText('已删除')).toHaveLength(2)

    fireEvent.click(screen.getAllByRole('button', { name: '恢复班级' })[0])
    expect(await screen.findByText('班级“A 班”已恢复。')).toBeInTheDocument()
    expect(screen.getByText('正常')).toBeInTheDocument()
  })
})
