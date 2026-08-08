import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TeacherAssignments } from './TeacherAssignments'

describe('TeacherAssignments', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('publishes a timed assignment with a case-version and roster snapshot', async () => {
    let assignments: unknown[] = []
    const options = {
      case_versions: [
        { id: 'version-1', case_code: 'OM-001', title: '牙周病例', version_number: 1, suggested_duration_minutes: 20 },
      ],
      class_groups: [
        { id: 'class-1', class_code: 'CLASS-A', class_name: 'A 班', student_count: 12 },
      ],
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) return Promise.resolve(new Response('{"csrf_token":"csrf"}', { status: 200 }))
      if (url.endsWith('/teacher/assignments/options/')) {
        return Promise.resolve(new Response(JSON.stringify(options), { status: 200 }))
      }
      if (url.endsWith('/teacher/assignments/') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        expect(body).toMatchObject({
          title: '牙周问诊考试',
          case_version_id: 'version-1',
          class_group_id: 'class-1',
          duration_minutes: 25,
        })
        const assignment = {
          id: 'assignment-1',
          ...body,
          case_title: '牙周病例',
          case_version_number: 1,
          class_code: 'CLASS-A',
          class_name: 'A 班',
          status: 'open',
          feedback_released_at: null,
          student_count: 12,
          not_started_count: 12,
          active_count: 0,
          submitted_count: 0,
          expired_count: 0,
          created_at: '2026-08-04T00:00:00Z',
        }
        assignments = [assignment]
        return Promise.resolve(new Response(JSON.stringify(assignment), { status: 201 }))
      }
      if (url.endsWith('/teacher/assignments/')) {
        return Promise.resolve(new Response(JSON.stringify(assignments), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<TeacherAssignments />)
    await waitFor(() => screen.getByRole('button', { name: '发布新任务' }))
    expect(screen.queryByText('EXAM ASSIGNMENTS')).not.toBeInTheDocument()
    expect(screen.queryByText('选择已发布病例和有学生的班级，为整场问诊设置限时。')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '发布新任务' }))
    await waitFor(() => screen.getByRole('option', { name: /OM-001/ }))
    expect(screen.getByRole('option', { name: 'A 班' })).toBeInTheDocument()
    expect(screen.queryByText('CLASS-A')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('任务名称'), { target: { value: '牙周问诊考试' } })
    fireEvent.change(screen.getByLabelText('病例版本'), { target: { value: 'version-1' } })
    fireEvent.change(screen.getByLabelText('班级'), { target: { value: 'class-1' } })
    fireEvent.change(screen.getByLabelText('整场限时（分钟）'), { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: '确认发布任务' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: '牙周问诊考试' })).toBeInTheDocument())
    expect(screen.getAllByText('12', { selector: 'strong' })).toHaveLength(2)
  })
})
