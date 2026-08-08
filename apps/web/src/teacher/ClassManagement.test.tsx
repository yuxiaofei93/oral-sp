import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ClassManagement } from './ClassManagement'

const classRecord = {
  id: 'class-1',
  code: 'CLASS-A',
  name: 'A 班',
  created_by_name: '教师甲',
  is_active: true,
  student_count: 1,
  students: [{
    id: 'student-1',
    email: 'student@example.com',
    display_name: '学生甲',
    created_at: '2026-08-04T00:00:00Z',
  }],
  created_at: '2026-08-04T00:00:00Z',
}

describe('ClassManagement', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('lists classes and opens the student roster', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([classRecord]), { status: 200 }),
    )

    render(<ClassManagement />)
    await waitFor(() => screen.getByRole('heading', { name: 'A 班' }))
    expect(screen.queryByText('创建班级并查看学生名单；学生注册时可自行选择有效班级。')).not.toBeInTheDocument()
    expect(screen.getByText('1 名学生')).toBeInTheDocument()
    expect(screen.getByText('正常')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '冻结班级' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '管理学生' }))

    expect(screen.getByRole('heading', { name: 'A 班学生名单' })).toBeInTheDocument()
    expect(screen.getByText('学生甲')).toBeInTheDocument()
    expect(screen.getByText('student@example.com')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '删除班级' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '转班' })).toBeDisabled()
  })

  it('lists frozen classes and supports freezing and reactivating a class', async () => {
    const frozenClass = {
      ...classRecord,
      id: 'class-2',
      code: 'CLASS-B',
      name: 'B 班',
      is_active: false,
      student_count: 0,
      students: [],
    }
    let classes = [classRecord, frozenClass]
    vi.spyOn(globalThis, 'confirm').mockReturnValue(true)
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"teacher-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/teacher/teaching/classes/class-1/') && init?.method === 'PATCH') {
        const { is_active: isActive } = JSON.parse(String(init.body)) as { is_active: boolean }
        classes = classes.map((item) => item.id === 'class-1'
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
    await waitFor(() => expect(screen.getByText('已冻结')).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'B 班' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '冻结班级' }))
    expect(await screen.findByText('班级“A 班”已冻结，历史记录保持不变。')).toBeInTheDocument()
    expect(screen.getAllByText('已冻结')).toHaveLength(2)

    fireEvent.click(screen.getAllByRole('button', { name: '激活班级' })[0])
    expect(await screen.findByText('班级“A 班”已激活。')).toBeInTheDocument()
    expect(screen.getByText('正常')).toBeInTheDocument()
  })

  it('creates a class without selecting a course', async () => {
    let classes: unknown[] = []
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"teacher-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/teacher/teaching/classes/') && init?.method === 'POST') {
        expect(JSON.parse(String(init.body))).toEqual({ code: 'CLASS-B', name: 'B 班' })
        const created = {
          ...classRecord,
          id: 'class-2',
          code: 'CLASS-B',
          name: 'B 班',
          student_count: 0,
          students: [],
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
    expect(screen.queryByLabelText('所属课程')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('班级编号'), { target: { value: 'class-b' } })
    fireEvent.change(screen.getByLabelText('班级名称'), { target: { value: 'B 班' } })
    fireEvent.click(screen.getByRole('button', { name: '创建班级' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'B 班' })).toBeInTheDocument())
    expect(screen.getByText('班级已创建，学生注册时可以选择该班级。')).toBeInTheDocument()
  })

  it('transfers a student to another class while keeping historical rosters', async () => {
    const targetClass = {
      ...classRecord,
      id: 'class-2',
      code: 'CLASS-B',
      name: 'B 班',
      student_count: 0,
      students: [],
    }
    let classes = [classRecord, targetClass]
    vi.spyOn(globalThis, 'confirm').mockReturnValue(true)
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"teacher-csrf"}', { status: 200 }))
      }
      if (
        url.endsWith('/teacher/teaching/classes/class-1/students/student-1/')
        && init?.method === 'PATCH'
      ) {
        expect(JSON.parse(String(init.body))).toEqual({ target_class_id: 'class-2' })
        classes = [
          { ...classRecord, student_count: 0, students: [] },
          { ...targetClass, student_count: 1, students: classRecord.students },
        ]
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      if (url.endsWith('/teacher/teaching/classes/')) {
        return Promise.resolve(new Response(JSON.stringify(classes), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<ClassManagement />)
    await waitFor(() => expect(screen.getAllByRole('button', { name: '管理学生' })).toHaveLength(2))
    fireEvent.click(screen.getAllByRole('button', { name: '管理学生' })[0])
    fireEvent.click(screen.getByRole('button', { name: '转班' }))
    expect(screen.getByLabelText('选择学生甲的目标班级')).toHaveValue('class-2')
    fireEvent.click(screen.getByRole('button', { name: '确认转班' }))

    expect(await screen.findByText('学生已转入“B 班”，已有任务名单保持不变。')).toBeInTheDocument()
    expect(screen.getByText('班级中还没有学生。')).toBeInTheDocument()
  })
})
