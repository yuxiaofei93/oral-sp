import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CourseManagement } from './CourseManagement'

describe('CourseManagement', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('creates and deletes a course from the course list', async () => {
    let courses: unknown[] = []
    vi.spyOn(globalThis, 'confirm').mockReturnValue(true)
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"teacher-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/teacher/teaching/courses/') && init?.method === 'POST') {
        expect(JSON.parse(String(init.body))).toEqual({ code: 'ORAL-2026', name: '口腔问诊训练' })
        const course = {
          id: 'course-1', code: 'ORAL-2026', name: '口腔问诊训练', is_active: true,
          class_count: 0, created_at: '2026-08-04T00:00:00Z', updated_at: '2026-08-04T00:00:00Z',
        }
        courses = [course]
        return Promise.resolve(new Response(JSON.stringify(course), { status: 201 }))
      }
      if (url.endsWith('/teacher/teaching/courses/course-1/') && init?.method === 'DELETE') {
        courses = []
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      if (url.endsWith('/teacher/teaching/courses/')) {
        return Promise.resolve(new Response(JSON.stringify(courses), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<CourseManagement />)
    await waitFor(() => screen.getByText('目前没有课程。'))
    fireEvent.change(screen.getByLabelText('课程编号'), { target: { value: 'oral-2026' } })
    fireEvent.change(screen.getByLabelText('课程名称'), { target: { value: '口腔问诊训练' } })
    fireEvent.click(screen.getByRole('button', { name: '创建课程' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: '口腔问诊训练' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '删除课程' }))
    await waitFor(() => expect(screen.getByText('课程已删除，历史任务和记录保持不变。')).toBeInTheDocument())
    expect(screen.queryByRole('heading', { name: '口腔问诊训练' })).not.toBeInTheDocument()
  })
})
