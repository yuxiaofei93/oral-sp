import { FormEvent, useEffect, useState } from 'react'

import {
  ApiError,
  CurrentUser,
  getCurrentUser,
  register,
  signIn,
  signOut,
} from '../api/client'
import { StudentAssignments } from '../student/StudentAssignments'
import { TeacherWorkspace } from '../teacher/TeacherWorkspace'

type Mode = 'login' | 'register'
type Portal = 'student' | 'teacher'

const roleNames = {
  student: '学生',
  teacher: '教师',
  administrator: '管理员',
}

type AuthPanelProps = {
  portal: Portal
}

function canAccessPortal(user: CurrentUser, portal: Portal) {
  return portal === 'student'
    ? user.roles.includes('student')
    : user.roles.some((role) => role === 'teacher' || role === 'administrator')
}

export function AuthPanel({ portal }: AuthPanelProps) {
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
    const passwordConfirmation = String(data.get('password_confirmation') ?? '')
    const displayName = String(data.get('display_name') ?? '')

    if (mode === 'register' && password !== passwordConfirmation) {
      setError('两次输入的密码不一致。')
      setSubmitting(false)
      return
    }

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
    if (!canAccessPortal(user, portal)) {
      const expectedRole = portal === 'student' ? '学生' : '教师或管理员'
      const otherPortal = portal === 'student' ? '/teacher/' : '/student/'
      const otherPortalName = portal === 'student' ? '教师端' : '学生端'

      return (
        <section className="auth-card auth-card--mismatch" aria-labelledby="role-mismatch-title">
          <p className="auth-card__hint">入口与账号角色不一致</p>
          <h2 id="role-mismatch-title">当前账号无法进入{portal === 'student' ? '学生端' : '教师端'}</h2>
          <p className="account-meta">
            当前登录的是 {user.display_name}（{user.roles.map((role) => roleNames[role]).join('、')}），
            此入口仅供{expectedRole}使用。
          </p>
          <div className="auth-card__actions">
            <a className="button button--link" href={otherPortal}>前往{otherPortalName}</a>
            <button className="button button--secondary" onClick={handleLogout} disabled={submitting}>
              退出当前账号
            </button>
          </div>
          {error && <p className="form-error">{error}</p>}
        </section>
      )
    }

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
          <TeacherWorkspace />
        ) : (
          <StudentAssignments />
        )}
      </div>
    )
  }

  return (
    <section
      className="auth-card"
      aria-label={portal === 'student' ? (mode === 'login' ? '学生登录' : '学生注册') : undefined}
      aria-labelledby={portal === 'teacher' ? 'auth-title' : undefined}
    >
      {portal === 'teacher' && <h2 id="auth-title">教师登录</h2>}
      <p className="auth-card__hint">
        {portal === 'teacher'
          ? '请使用已由管理员授权的教师或管理员账号登录。'
          : '使用中国大陆手机号和密码，暂不发送短信验证码。'}
      </p>

      <form onSubmit={handleSubmit}>
        {mode === 'register' && (
          <label>
            姓名
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
        {mode === 'register' && (
          <label>
            确认密码
            <input
              name="password_confirmation"
              type="password"
              autoComplete="new-password"
              minLength={8}
              required
            />
          </label>
        )}
        {error && <p className="form-error">{error}</p>}
        <button className="button" type="submit" disabled={submitting}>
          {submitting
            ? '正在提交…'
            : mode === 'register'
              ? '注册'
              : portal === 'student' ? '登录' : '进入教师端'}
        </button>
        {portal === 'student' && (
          <p className="auth-alternative">
            {mode === 'login' ? '还没有账号？' : '已有账号？'}
            <button
              type="button"
              onClick={() => {
                setMode(mode === 'login' ? 'register' : 'login')
                setError('')
              }}
            >
              {mode === 'login' ? '注册' : '返回登录'}
            </button>
          </p>
        )}
      </form>
    </section>
  )
}
