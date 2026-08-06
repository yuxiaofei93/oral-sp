import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthPanel } from './AuthPanel'

describe('AuthPanel', () => {
  afterEach(() => {
    cleanup()
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
    await waitFor(() => screen.getByRole('option', { name: 'CLASS-A · A 班（教师甲）' }))
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'student@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: '获取验证码' }))
    expect(await screen.findByText('验证码已发送，请查收邮件。')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('姓名'), { target: { value: '测试学生' } })
    fireEvent.change(screen.getByLabelText('班级'), { target: { value: 'class-1' } })
    fireEvent.change(screen.getByLabelText('邮箱验证码'), { target: { value: '123456' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'MolarTraining!2026' } })
    fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'MolarTraining!2026' } })
    fireEvent.click(screen.getByRole('button', { name: '注册' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: '欢迎，测试学生' })).toBeInTheDocument())
    expect(screen.getByText(/student@example.com/)).toBeInTheDocument()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(7))
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
    await waitFor(() => screen.getByRole('option', { name: 'CLASS-A · A 班（教师甲）' }))
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
    await screen.findByText('验证码已发送，请查收邮件。')
    fireEvent.change(screen.getByLabelText('邮箱验证码'), { target: { value: '654321' } })
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'NewMolarTraining!2026' } })
    fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'NewMolarTraining!2026' } })
    fireEvent.click(screen.getByRole('button', { name: '重置密码' }))

    expect(await screen.findByText('密码已重置，请使用新密码登录。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(5)
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
    expect(screen.queryByRole('heading', { name: '我的问诊任务' })).not.toBeInTheDocument()
  })
})
