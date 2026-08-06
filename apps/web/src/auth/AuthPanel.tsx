import { FormEvent, useEffect, useState } from 'react'

import {
  ApiError,
  CurrentUser,
  RegistrationClass,
  getCurrentUser,
  listRegistrationClasses,
  register,
  requestPasswordResetCode,
  requestRegistrationCode,
  resetPassword,
  signIn,
  signOut,
} from '../api/client'
import { StudentAssignments } from '../student/StudentAssignments'
import { TeacherWorkspace } from '../teacher/TeacherWorkspace'
import { portalHome } from '../portal'

type Mode = 'login' | 'register' | 'forgot_password'
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
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [codeSending, setCodeSending] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [registrationClasses, setRegistrationClasses] = useState<RegistrationClass[] | null>(null)
  const [registrationClassesLoading, setRegistrationClassesLoading] = useState(false)

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

  function changeMode(nextMode: Mode) {
    setMode(nextMode)
    setError('')
    setNotice('')
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setNotice('')

    const data = new FormData(event.currentTarget)
    const password = String(data.get('password') ?? '')
    const passwordConfirmation = String(data.get('password_confirmation') ?? '')
    const verificationCode = String(data.get('verification_code') ?? '')
    const displayName = String(data.get('display_name') ?? '')
    const classGroupId = String(data.get('class_group_id') ?? '')

    if (mode !== 'login' && password !== passwordConfirmation) {
      setError('两次输入的密码不一致。')
      setSubmitting(false)
      return
    }
    if (mode === 'register' && !classGroupId) {
      setError('请选择班级。')
      setSubmitting(false)
      return
    }

    try {
      if (mode === 'forgot_password') {
        const result = await resetPassword({
          email,
          verification_code: verificationCode,
          new_password: password,
        })
        changeMode('login')
        setNotice(result.detail)
        return
      }
      const nextUser = mode === 'register'
        ? await register({
            email,
            password,
            verification_code: verificationCode,
            display_name: displayName,
            class_group_id: classGroupId,
          })
        : await signIn({ email, password })
      setUser(nextUser)
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '请求失败，请稍后重试。')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleSendCode() {
    if (!email.trim() || !email.includes('@')) {
      setError('请先输入有效的邮箱地址。')
      return
    }
    setCodeSending(true)
    setError('')
    setNotice('')
    try {
      if (mode === 'register') {
        await requestRegistrationCode(email)
      } else {
        await requestPasswordResetCode(email)
      }
      setNotice('验证码已发送。使用本地邮件模式时，请查看后端终端。')
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '验证码发送失败，请稍后重试。')
    } finally {
      setCodeSending(false)
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

  async function showRegistration() {
    changeMode('register')
    if (registrationClasses !== null || registrationClassesLoading) return
    setRegistrationClassesLoading(true)
    try {
      setRegistrationClasses(await listRegistrationClasses())
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '班级列表加载失败。')
      setRegistrationClasses([])
    } finally {
      setRegistrationClassesLoading(false)
    }
  }

  if (user === undefined) {
    return <section className="auth-card auth-card--loading">正在读取账号状态…</section>
  }

  if (user) {
    if (!canAccessPortal(user, portal)) {
      const expectedRole = portal === 'student' ? '学生' : '教师或管理员'
      const otherPortal = portalHome(portal === 'student' ? 'teacher' : 'student')
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
              {user.email} · {user.roles.map((role) => roleNames[role]).join('、')}
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
      aria-label={portal === 'student' ? '账号认证' : undefined}
      aria-labelledby={portal === 'teacher' ? 'auth-title' : undefined}
    >
      {portal === 'teacher' && (
        <h2 id="auth-title">{mode === 'forgot_password' ? '重置密码' : '教师登录'}</h2>
      )}
      <p className="auth-card__hint">
        {mode === 'forgot_password'
          ? '通过邮箱验证码设置新密码。'
          : portal === 'teacher'
            ? '请使用已由管理员授权的教师或管理员账号登录。'
            : mode === 'register'
              ? '使用邮箱创建账号并加入班级。'
              : '使用邮箱和密码登录。'}
      </p>

      <form onSubmit={handleSubmit}>
        {mode === 'register' && (
          <label>
            姓名
            <input name="display_name" autoComplete="name" required maxLength={80} />
          </label>
        )}
        {mode === 'register' && (
          <label>
            班级
            <select
              name="class_group_id"
              required
              disabled={registrationClassesLoading || registrationClasses?.length === 0}
            >
              <option value="">
                {registrationClassesLoading
                  ? '正在加载班级…'
                  : registrationClasses?.length === 0
                    ? '暂无可选班级，请联系教师'
                    : '请选择班级'}
              </option>
              {registrationClasses?.map((classGroup) => (
                <option value={classGroup.id} key={classGroup.id}>
                  {classGroup.course_name} / {classGroup.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          邮箱
          <input
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        {mode !== 'login' && (
          <label>
            邮箱验证码
            <span className="verification-field">
              <input
                name="verification_code"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                autoComplete="one-time-code"
                required
              />
              <button
                className="button button--secondary"
                type="button"
                disabled={codeSending}
                onClick={handleSendCode}
              >
                {codeSending ? '发送中…' : '获取验证码'}
              </button>
            </span>
          </label>
        )}
        <label>
          {mode === 'forgot_password' ? '新密码' : '密码'}
          <input
            name="password"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            minLength={8}
            required
          />
        </label>
        {mode !== 'login' && (
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
        {notice && <p className="form-success">{notice}</p>}
        <button
          className="button"
          type="submit"
          disabled={submitting || (mode === 'register' && registrationClasses?.length === 0)}
        >
          {submitting
            ? '正在提交…'
            : mode === 'register'
              ? '注册'
              : mode === 'forgot_password'
                ? '重置密码'
                : '登录'}
        </button>
        <p className="auth-alternative">
          {mode === 'login' ? (
            <>
              {portal === 'student' && <><span>还没有账号？</span><button type="button" onClick={() => void showRegistration()}>注册</button></>}
              <button type="button" onClick={() => changeMode('forgot_password')}>忘记密码</button>
            </>
          ) : (
            <button type="button" onClick={() => changeMode('login')}>返回登录</button>
          )}
        </p>
      </form>
    </section>
  )
}
