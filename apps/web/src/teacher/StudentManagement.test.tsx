import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { StudentManagement } from './StudentManagement'

const firstClass = {
  id: 'class-1',
  code: 'CLASS-A',
  name: '口腔一班',
  created_by_name: '教师甲',
  is_active: true,
  student_count: 1,
  students: [],
  created_at: '2026-08-01T00:00:00Z',
}

const secondClass = {
  ...firstClass,
  id: 'class-2',
  code: 'CLASS-B',
  name: '口腔二班',
  student_count: 0,
}

const student = {
  id: 'student-1',
  display_name: '林晓雅',
  email: 'lin@example.com',
  classes: [{
    id: 'class-1',
    code: 'CLASS-A',
    name: '口腔一班',
    is_active: true,
  }],
  is_active: true,
  date_joined: '2026-08-04T00:00:00Z',
}

describe('StudentManagement', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows the student list by default and filters by name, email, and class', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = new URL(String(input), 'http://localhost')
      if (url.pathname.endsWith('/classes/')) {
        return Promise.resolve(new Response(JSON.stringify([firstClass, secondClass]), { status: 200 }))
      }
      if (url.pathname.endsWith('/students/')) {
        return Promise.resolve(new Response(JSON.stringify([student]), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<StudentManagement />)

    expect(await screen.findByText('林晓雅')).toBeInTheDocument()
    expect(screen.getByText('lin@example.com')).toBeInTheDocument()
    expect(screen.getAllByText('口腔一班')).toHaveLength(2)
    expect(screen.queryByText('CLASS-A')).not.toBeInTheDocument()
    expect(screen.getByText('正常')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('姓名'), { target: { value: '林' } })
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'lin@' } })
    fireEvent.change(screen.getByLabelText('班级'), { target: { value: 'class-1' } })
    fireEvent.click(screen.getByRole('button', { name: '筛选' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/teacher/teaching/students/?name=%E6%9E%97&email=lin%40&class_group_id=class-1',
        { credentials: 'same-origin' },
      )
    })
  })

  it('opens student details and lets an administrator adjust the class', async () => {
    const updatedStudent = {
      ...student,
      classes: [{
        id: 'class-2',
        code: 'CLASS-B',
        name: '口腔二班',
        is_active: true,
      }],
    }
    vi.spyOn(globalThis, 'confirm').mockReturnValue(true)
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/classes/')) {
        return Promise.resolve(new Response(JSON.stringify([firstClass, secondClass]), { status: 200 }))
      }
      if (url.endsWith('/students/')) {
        return Promise.resolve(new Response(JSON.stringify([student]), { status: 200 }))
      }
      if (url.endsWith('/students/student-1/') && init?.method === 'PATCH') {
        expect(JSON.parse(String(init.body))).toEqual({ class_group_id: 'class-2' })
        return Promise.resolve(new Response(JSON.stringify(updatedStudent), { status: 200 }))
      }
      if (url.endsWith('/students/student-1/')) {
        return Promise.resolve(new Response(JSON.stringify(student), { status: 200 }))
      }
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"admin-csrf"}', { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<StudentManagement />)
    await screen.findByText('林晓雅')
    fireEvent.click(screen.getByRole('button', { name: '查看详情' }))

    expect(await screen.findByRole('heading', { name: '林晓雅' })).toBeInTheDocument()
    expect(screen.getAllByText('lin@example.com')).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: '调整班级' }))
    expect(screen.getByRole('button', { name: '保存调整' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('调整到班级'), { target: { value: 'class-2' } })
    fireEvent.click(screen.getByRole('button', { name: '保存调整' }))

    expect(await screen.findByText('已将林晓雅调整到“口腔二班”。')).toBeInTheDocument()
    expect(screen.getAllByText('口腔二班')).toHaveLength(3)
  })
})
