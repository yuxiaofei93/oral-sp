import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthPanel } from './AuthPanel'

describe('AuthPanel', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('registers a student with a CSRF-protected request', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/me/')) {
        return Promise.resolve(new Response('{"detail":"not authenticated"}', { status: 403 }))
      }
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"test-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/register/')) {
        expect(init?.headers).toMatchObject({ 'X-CSRFToken': 'test-csrf' })
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 'user-1',
              phone: '+8613800138000',
              display_name: '测试学生',
              roles: ['student'],
            }),
            { status: 201 },
          ),
        )
      }
      if (url.endsWith('/student/assignments/')) {
        return Promise.resolve(new Response('[]', { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<AuthPanel portal="student" />)
    await waitFor(() => screen.getByRole('heading', { name: '学生登录' }))
    fireEvent.click(screen.getByRole('button', { name: '学生注册' }))
    fireEvent.change(screen.getByLabelText('姓名或教学昵称'), { target: { value: '测试学生' } })
    fireEvent.change(screen.getByLabelText('手机号'), { target: { value: '13800138000' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'MolarTraining!2026' } })
    fireEvent.click(screen.getByRole('button', { name: '注册并进入学生端' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: '欢迎，测试学生' })).toBeInTheDocument())
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4))
  })

  it('does not render a student workspace inside the teacher portal', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/me/')) {
        return Promise.resolve(new Response(JSON.stringify({
          id: 'student-1',
          phone: '+8613800138000',
          display_name: '测试学生',
          roles: ['student'],
        }), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<AuthPanel portal="teacher" />)

    await waitFor(() => expect(screen.getByRole('heading', {
      name: '当前账号无法进入教师端',
    })).toBeInTheDocument())
    expect(screen.getByRole('link', { name: '前往学生端' })).toHaveAttribute('href', '/student/')
    expect(screen.queryByRole('heading', { name: '我的问诊任务' })).not.toBeInTheDocument()
  })
})
