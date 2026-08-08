import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthPanel } from './AuthPanel'

describe('AuthPanel', () => {
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('requests an email code and registers a student with CSRF protection', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/me/')) {
        return Promise.resolve(new Response('{"detail":"not authenticated"}', { status: 403 }))
      }
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"test-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/registration-classes/')) {
        return Promise.resolve(new Response(JSON.stringify([{
          id: 'class-1', code: 'CLASS-A', name: 'A 班',
          teacher_name: '教师甲',
        }]), { status: 200 }))
      }
      if (url.endsWith('/verification-codes/registration/')) {
        expect(init?.headers).toMatchObject({ 'X-CSRFToken': 'test-csrf' })
        expect(JSON.parse(String(init?.body))).toEqual({ email: 'student@example.com' })
        return Promise.resolve(new Response(JSON.stringify({
          detail: '验证码已发送。', expires_in: 600,
        }), { status: 200 }))
      }
      if (url.endsWith('/register/')) {
        expect(init?.headers).toMatchObject({ 'X-CSRFToken': 'test-csrf' })
        expect(JSON.parse(String(init?.body))).toEqual({
          email: 'student@example.com',
          verification_code: '123456',
          password: 'MolarTraining!2026',
          display_name: '测试学生',
          class_group_id: 'class-1',
        })
        return Promise.resolve(new Response(JSON.stringify({
          id: 'user-1',
          email: 'student@example.com',
          display_name: '测试学生',
          roles: ['student'],
          class_names: ['A 班'],
        }), { status: 201 }))
      }
      if (url.endsWith('/student/assignments/')) {
        return Promise.resolve(new Response('[]', { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<AuthPanel portal="student" />)
    await waitFor(() => screen.getByRole('button', { name: '登录' }))
    fireEvent.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => screen.getByRole('option', { name: 'A 班' }))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'student@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: '获取验证码' }))
    expect(await screen.findByRole('dialog', { name: '确认邮箱地址' })).toBeInTheDocument()
    expect(screen.getByText('student@example.com')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(screen.queryByRole('dialog', { name: '确认邮箱地址' })).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)

    fireEvent.click(screen.getByRole('button', { name: '获取验证码' }))
    await screen.findByRole('dialog', { name: '确认邮箱地址' })
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: '确认发送' }))
    await act(async () => {
      for (let step = 0; step < 10; step += 1) await Promise.resolve()
    })
    expect(screen.getByText('验证码已发送，请查收邮件。')).toBeInTheDocument()

    const resendButton = screen.getByRole('button', { name: '60 秒后重试' })
    expect(resendButton).toBeDisabled()
    fireEvent.click(resendButton)
    expect(fetchMock).toHaveBeenCalledTimes(4)

    act(() => vi.advanceTimersByTime(1000))
    expect(screen.getByRole('button', { name: '59 秒后重试' })).toBeDisabled()

    for (let second = 0; second < 59; second += 1) {
      act(() => vi.advanceTimersByTime(1000))
    }
    expect(screen.getByRole('button', { name: '获取验证码' })).toBeEnabled()
    vi.useRealTimers()

    fireEvent.change(screen.getByLabelText('姓名'), { target: { value: '测试学生' } })
    fireEvent.change(screen.getByLabelText('班级'), { target: { value: 'class-1' } })
    fireEvent.change(screen.getByLabelText('邮箱验证码'), { target: { value: '123456' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'MolarTraining!2026' } })
    fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'MolarTraining!2026' } })
    fireEvent.click(screen.getByRole('button', { name: '注册' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: '你好，测试学生' })).toBeInTheDocument())
    expect(screen.queryByText('当前账号')).not.toBeInTheDocument()
    expect(screen.getByText('student@example.com · A 班 · 学生')).toBeInTheDocument()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(7))
  })

  it('shows the request ID when verification email delivery fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/me/')) {
        return Promise.resolve(new Response('{"detail":"not authenticated"}', { status: 403 }))
      }
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"test-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/registration-classes/')) {
        return Promise.resolve(new Response(JSON.stringify([{
          id: 'class-1', code: 'CLASS-A', name: 'A 班', teacher_name: '教师甲',
        }]), { status: 200 }))
      }
      if (url.endsWith('/verification-codes/registration/')) {
        return Promise.resolve(new Response(JSON.stringify({
          detail: '验证码邮件发送失败，请稍后重试。',
          request_id: 'mail-failure-123',
        }), {
          status: 503,
          headers: { 'X-Request-ID': 'mail-failure-123' },
        }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<AuthPanel portal="student" />)
    await waitFor(() => screen.getByRole('button', { name: '登录' }))
    fireEvent.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => screen.getByRole('option', { name: 'A 班' }))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'student@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: '获取验证码' }))
    await screen.findByRole('dialog', { name: '确认邮箱地址' })
    fireEvent.click(screen.getByRole('button', { name: '确认发送' }))

    expect(await screen.findByText(
      '验证码邮件发送失败，请稍后重试。（问题编号：mail-failure-123）',
    )).toBeInTheDocument()
  })

  it('rejects mismatched registration passwords before calling the registration API', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/me/')) {
        return Promise.resolve(new Response('{"detail":"not authenticated"}', { status: 403 }))
      }
      if (url.endsWith('/registration-classes/')) {
        return Promise.resolve(new Response(JSON.stringify([{
          id: 'class-1', code: 'CLASS-A', name: 'A 班',
          teacher_name: '教师甲',
        }]), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<AuthPanel portal="student" />)
    await waitFor(() => screen.getByRole('button', { name: '登录' }))
    fireEvent.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => screen.getByRole('option', { name: 'A 班' }))
    fireEvent.change(screen.getByLabelText('姓名'), { target: { value: '测试学生' } })
    fireEvent.change(screen.getByLabelText('班级'), { target: { value: 'class-1' } })
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'student@example.com' } })
    fireEvent.change(screen.getByLabelText('邮箱验证码'), { target: { value: '123456' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'MolarTraining!2026' } })
    fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'different-password' } })
    fireEvent.click(screen.getByRole('button', { name: '注册' }))

    expect(await screen.findByText('两次输入的密码不一致。')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('resets a password with an email verification code', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/me/')) {
        return Promise.resolve(new Response('{"detail":"not authenticated"}', { status: 403 }))
      }
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"test-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/verification-codes/password-reset/')) {
        return Promise.resolve(new Response(JSON.stringify({
          detail: '如果该邮箱已注册，验证码将发送到邮箱。',
        }), { status: 200 }))
      }
      if (url.endsWith('/password-reset/')) {
        expect(JSON.parse(String(init?.body))).toEqual({
          email: 'teacher@example.com',
          verification_code: '654321',
          new_password: 'NewMolarTraining!2026',
        })
        return Promise.resolve(new Response(JSON.stringify({
          detail: '密码已重置，请使用新密码登录。',
        }), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<AuthPanel portal="teacher" />)
    await waitFor(() => screen.getByRole('button', { name: '登录' }))
    fireEvent.click(screen.getByRole('button', { name: '忘记密码' }))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'teacher@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: '获取验证码' }))
    expect(await screen.findByRole('dialog', { name: '确认邮箱地址' })).toBeInTheDocument()
    expect(screen.getByText('teacher@example.com')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认发送' }))
    await screen.findByText('验证码已发送，请查收邮件。')
    fireEvent.change(screen.getByLabelText('邮箱验证码'), { target: { value: '654321' } })
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'NewMolarTraining!2026' } })
    fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'NewMolarTraining!2026' } })
    fireEvent.click(screen.getByRole('button', { name: '重置密码' }))

    expect(await screen.findByText('密码已重置，请使用新密码登录。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(5)
  })

  it('keeps the login email but clears the password when opening password reset', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/me/')) {
        return Promise.resolve(new Response('{"detail":"not authenticated"}', { status: 403 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<AuthPanel portal="teacher" />)
    await waitFor(() => screen.getByRole('button', { name: '登录' }))

    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'teacher@example.com' } })
    const loginPassword = screen.getByLabelText('密码')
    fireEvent.change(loginPassword, { target: { value: 'ExistingPassword!2026' } })
    expect(loginPassword).toHaveAttribute('type', 'password')

    fireEvent.click(screen.getByRole('button', { name: '显示密码' }))
    expect(loginPassword).toHaveAttribute('type', 'text')
    expect(screen.getByRole('button', { name: '隐藏密码' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: '隐藏密码' }))
    expect(loginPassword).toHaveAttribute('type', 'password')
    fireEvent.click(screen.getByRole('button', { name: '忘记密码' }))

    expect(screen.getByLabelText('邮箱')).toHaveValue('teacher@example.com')
    expect(screen.getByLabelText('新密码')).toHaveValue('')
    expect(screen.getByLabelText('确认密码')).toHaveValue('')
    expect(screen.getAllByRole('button', { name: '显示密码' })).toHaveLength(2)
  })

  it('does not render a student workspace inside the teacher portal', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/me/')) {
        return Promise.resolve(new Response(JSON.stringify({
          id: 'student-1',
          email: 'student@example.com',
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
    expect(screen.getByRole('link', { name: '前往学生端' })).toHaveAttribute(
      'href',
      'http://localhost:5173/',
    )
    expect(screen.queryByRole('heading', { name: '问诊任务' })).not.toBeInTheDocument()
  })
})
