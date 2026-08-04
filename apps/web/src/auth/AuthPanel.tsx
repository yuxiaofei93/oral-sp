import { FormEvent, useEffect, useState } from 'react'

import {
  ApiError,
  CurrentUser,
  getCurrentUser,
  register,
  signIn,
  signOut,
} from '../api/client'
import { TeacherCases } from '../teacher/TeacherCases'
import { StudentAssignments } from '../student/StudentAssignments'

type Mode = 'login' | 'register'

const roleNames = {
  student: '学生',
  teacher: '教师',
  administrator: '管理员',
}

export function AuthPanel() {
  const [mode, setMode] = useState<Mode>('login')
  const [user, setUser] = useState<CurrentUser | null>()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getCurrentUser()
      .then(setUser)
      .catch((requestError: unknown) => {
        if (requestError instanceof ApiError && [401, 403].includes(requestError.status)) {
          setUser(null)
          return
        }
        setError('暂时无法读取登录状态。')
        setUser(null)
      })
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')

    const data = new FormData(event.currentTarget)
    const phone = String(data.get('phone') ?? '')
    const password = String(data.get('password') ?? '')
    const displayName = String(data.get('display_name') ?? '')

    try {
      const nextUser =
        mode === 'register'
          ? await register({ phone, password, display_name: displayName })
          : await signIn({ phone, password })
      setUser(nextUser)
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '请求失败，请稍后重试。')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleLogout() {
    setSubmitting(true)
    setError('')
    try {
      await signOut()
      setUser(null)
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '退出失败，请稍后重试。')
    } finally {
      setSubmitting(false)
    }
  }

  if (user === undefined) {
    return <section className="auth-card auth-card--loading">正在读取账号状态…</section>
  }

  if (user) {
    return (
      <div className="authenticated-area">
        <section className="auth-card auth-card--account" aria-labelledby="welcome-title">
          <div>
            <p className="auth-card__hint">当前账号</p>
            <h2 id="welcome-title">欢迎，{user.display_name}</h2>
            <p className="account-meta">
              {user.phone} · {user.roles.map((role) => roleNames[role]).join('、')}
            </p>
          </div>
          <button className="button button--secondary" onClick={handleLogout} disabled={submitting}>
            退出登录
          </button>
          {error && <p className="form-error">{error}</p>}
        </section>
        {user.roles.some((role) => role === 'teacher' || role === 'administrator') ? (
          <TeacherCases />
        ) : (
          <StudentAssignments />
        )}
      </div>
    )
  }

  return (
    <section className="auth-card" aria-labelledby="auth-title">
      <div className="auth-switch" aria-label="账号入口">
        <button
          className={mode === 'login' ? 'is-active' : ''}
          type="button"
          onClick={() => setMode('login')}
        >
          登录
        </button>
        <button
          className={mode === 'register' ? 'is-active' : ''}
          type="button"
          onClick={() => setMode('register')}
        >
          学生注册
        </button>
      </div>

      <h2 id="auth-title">{mode === 'login' ? '进入教学平台' : '创建学生账号'}</h2>
      <p className="auth-card__hint">使用中国大陆手机号和密码，暂不发送短信验证码。</p>

      <form onSubmit={handleSubmit}>
        {mode === 'register' && (
          <label>
            姓名或教学昵称
            <input name="display_name" autoComplete="name" required maxLength={80} />
          </label>
        )}
        <label>
          手机号
          <input
            name="phone"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            placeholder="13800138000"
            required
          />
        </label>
        <label>
          密码
          <input
            name="password"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            minLength={8}
            required
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button className="button" type="submit" disabled={submitting}>
          {submitting ? '正在提交…' : mode === 'login' ? '登录' : '注册并登录'}
        </button>
      </form>
    </section>
  )
}
