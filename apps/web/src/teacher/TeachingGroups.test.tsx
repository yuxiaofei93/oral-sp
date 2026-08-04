import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TeachingGroups } from './TeachingGroups'

describe('TeachingGroups', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('creates a course through a CSRF-protected request', async () => {
    let courses: unknown[] = []
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"teacher-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/teacher/teaching/courses/') && init?.method === 'POST') {
        expect(init.headers).toMatchObject({ 'X-CSRFToken': 'teacher-csrf' })
        expect(JSON.parse(String(init.body))).toEqual({ code: 'ORAL-2026', name: '口腔问诊训练' })
        const course = {
          id: 'course-1',
          code: 'ORAL-2026',
          name: '口腔问诊训练',
          is_active: true,
          classes: [],
          created_at: '2026-08-04T00:00:00Z',
          updated_at: '2026-08-04T00:00:00Z',
        }
        courses = [course]
        return Promise.resolve(new Response(JSON.stringify(course), { status: 201 }))
      }
      if (url.endsWith('/teacher/teaching/courses/')) {
        return Promise.resolve(new Response(JSON.stringify(courses), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<TeachingGroups />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    fireEvent.change(screen.getByLabelText('课程编号'), { target: { value: 'oral-2026' } })
    fireEvent.change(screen.getByLabelText('课程名称'), { target: { value: '口腔问诊训练' } })
    fireEvent.click(screen.getByRole('button', { name: '创建课程' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: '口腔问诊训练' })).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalled()
  })

  it('imports a batch of student phone numbers into a selected class', async () => {
    let studentCount = 0
    const courseData = () => [
      {
        id: 'course-1',
        code: 'ORAL-2026',
        name: '口腔问诊训练',
        is_active: true,
        created_at: '2026-08-04T00:00:00Z',
        updated_at: '2026-08-04T00:00:00Z',
        classes: [
          {
            id: 'class-1',
            code: 'CLASS-A',
            name: 'A 班',
            is_active: true,
            student_count: studentCount,
            students: studentCount
              ? [{ id: 'student-1', phone: '+8613800138000', display_name: '学生甲', created_at: '2026-08-04T00:00:00Z' }]
              : [],
            created_at: '2026-08-04T00:00:00Z',
          },
        ],
      },
    ]
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) return Promise.resolve(new Response('{"csrf_token":"csrf"}', { status: 200 }))
      if (url.endsWith('/class-1/students/') && init?.method === 'POST') {
        expect(JSON.parse(String(init.body)).phones).toEqual(['13800138000', '13900139000'])
        studentCount = 1
        return Promise.resolve(new Response('{"created_count":1,"existing_count":0}', { status: 200 }))
      }
      if (url.endsWith('/teacher/teaching/courses/')) {
        return Promise.resolve(new Response(JSON.stringify(courseData()), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<TeachingGroups />)
    await waitFor(() => screen.getByRole('button', { name: /A 班/ }))
    fireEvent.click(screen.getByRole('button', { name: /A 班/ }))
    fireEvent.change(screen.getByPlaceholderText(/13800138000/), {
      target: { value: '13800138000\n13900139000' },
    })
    fireEvent.click(screen.getByRole('button', { name: '批量加入学生' }))

    await waitFor(() => expect(screen.getByText('学生甲')).toBeInTheDocument())
  })
})
