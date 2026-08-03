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
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<AuthPanel />)
    await waitFor(() => screen.getByRole('heading', { name: '进入教学平台' }))
    fireEvent.click(screen.getByRole('button', { name: '学生注册' }))
    fireEvent.change(screen.getByLabelText('姓名或教学昵称'), { target: { value: '测试学生' } })
    fireEvent.change(screen.getByLabelText('手机号'), { target: { value: '13800138000' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'MolarTraining!2026' } })
    fireEvent.click(screen.getByRole('button', { name: '注册并登录' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: '欢迎，测试学生' })).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })
})

