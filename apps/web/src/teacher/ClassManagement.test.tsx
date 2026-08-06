import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ClassManagement } from './ClassManagement'

describe('ClassManagement', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('lists classes and opens the student roster', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/teacher/teaching/courses/')) {
        return Promise.resolve(new Response(JSON.stringify([{
          id: 'course-1', code: 'ORAL-2026', name: '口腔问诊训练', is_active: true,
          class_count: 1, created_at: '2026-08-04T00:00:00Z', updated_at: '2026-08-04T00:00:00Z',
        }]), { status: 200 }))
      }
      if (url.endsWith('/teacher/teaching/classes/')) {
        return Promise.resolve(new Response(JSON.stringify([{
          id: 'class-1', code: 'CLASS-A', name: 'A 班', course_id: 'course-1',
          course_code: 'ORAL-2026', course_name: '口腔问诊训练', is_active: true,
          student_count: 1,
          students: [{
            id: 'student-1', email: 'student@example.com', display_name: '学生甲',
            created_at: '2026-08-04T00:00:00Z',
          }],
          created_at: '2026-08-04T00:00:00Z',
        }]), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<ClassManagement />)
    await waitFor(() => screen.getByRole('heading', { name: 'A 班' }))
    expect(screen.getByText('1 名学生')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '管理学生' }))

    expect(screen.getByRole('heading', { name: 'A 班学生名单' })).toBeInTheDocument()
    expect(screen.getByText('学生甲')).toBeInTheDocument()
    expect(screen.getByText('student@example.com')).toBeInTheDocument()
  })

  it('creates a class under an existing course', async () => {
    let classes: unknown[] = []
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"teacher-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/teacher/teaching/courses/')) {
        return Promise.resolve(new Response(JSON.stringify([{
          id: 'course-1', code: 'ORAL-2026', name: '口腔问诊训练', is_active: true,
          class_count: classes.length, created_at: '2026-08-04T00:00:00Z',
          updated_at: '2026-08-04T00:00:00Z',
        }]), { status: 200 }))
      }
      if (url.endsWith('/teacher/teaching/classes/') && init?.method === 'POST') {
        expect(JSON.parse(String(init.body))).toEqual({
          course_id: 'course-1', code: 'CLASS-B', name: 'B 班',
        })
        const created = {
          id: 'class-2', code: 'CLASS-B', name: 'B 班', course_id: 'course-1',
          course_code: 'ORAL-2026', course_name: '口腔问诊训练', is_active: true,
          student_count: 0, students: [], created_at: '2026-08-04T00:00:00Z',
        }
        classes = [created]
        return Promise.resolve(new Response(JSON.stringify(created), { status: 201 }))
      }
      if (url.endsWith('/teacher/teaching/classes/')) {
        return Promise.resolve(new Response(JSON.stringify(classes), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<ClassManagement />)
    await waitFor(() => expect(screen.getByRole('button', { name: '创建班级' })).toBeEnabled())
    fireEvent.change(screen.getByLabelText('所属课程'), { target: { value: 'course-1' } })
    fireEvent.change(screen.getByLabelText('班级编号'), { target: { value: 'class-b' } })
    fireEvent.change(screen.getByLabelText('班级名称'), { target: { value: 'B 班' } })
    fireEvent.click(screen.getByRole('button', { name: '创建班级' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'B 班' })).toBeInTheDocument())
    expect(screen.getByText('班级已创建，学生注册时可以选择该班级。')).toBeInTheDocument()
  })
})
