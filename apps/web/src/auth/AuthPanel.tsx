import { FormEvent, useEffect, useId, useRef, useState } from 'react'

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
type CodeConfirmation = {
  email: string
  mode: Exclude<Mode, 'login'>
}

const CODE_RESEND_SECONDS = 60

const roleNames = {
  student: '学生',
  teacher: '教师',
  administrator: '管理员',
}

type AuthPanelProps = {
  portal: Portal
}

type PasswordFieldProps = {
  label: string
  name: string
  autoComplete: 'current-password' | 'new-password'
}

function PasswordField({ label, name, autoComplete }: PasswordFieldProps) {
  const inputId = useId()
  const [isVisible, setIsVisible] = useState(false)
  const toggleLabel = isVisible ? '隐藏密码' : '显示密码'

  return (
    <div className="password-form-field">
      <label htmlFor={inputId}>{label}</label>
      <span className="password-field">
        <input
          id={inputId}
          name={name}
          type={isVisible ? 'text' : 'password'}
          autoComplete={autoComplete}
          minLength={8}
          required
        />
        <button
          className="password-visibility"
          type="button"
          aria-label={toggleLabel}
          aria-pressed={isVisible}
          title={toggleLabel}
          onClick={() => setIsVisible((visible) => !visible)}
        >
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
            <circle cx="12" cy="12" r="2.5" />
            {isVisible && <path d="m4 4 16 16" />}
          </svg>
        </button>
      </span>
    </div>
  )
}

function canAccessPortal(user: CurrentUser, portal: Portal) {
  return portal === 'student'
    ? user.roles.includes('student')
    : user.roles.some((role) => role === 'teacher' || role === 'administrator')
}

function accountMeta(user: CurrentUser) {
  const details = [user.email]
  if (user.roles.includes('student')) details.push(...user.class_names)
  details.push(user.roles.map((role) => roleNames[role]).join('、'))
  return details.join(' · ')
}

export function AuthPanel({ portal }: AuthPanelProps) {
  const [mode, setMode] = useState<Mode>('login')
  const [user, setUser] = useState<CurrentUser | null>()
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [codeSending, setCodeSending] = useState(false)
  const [codeResendSeconds, setCodeResendSeconds] = useState(0)
  const codeSendingRef = useRef(false)
  const [codeConfirmation, setCodeConfirmation] = useState<CodeConfirmation | null>(null)
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

  useEffect(() => {
    if (codeResendSeconds <= 0) return

    const timer = window.setTimeout(() => {
      setCodeResendSeconds((seconds) => Math.max(0, seconds - 1))
    }, 1000)

    return () => window.clearTimeout(timer)
  }, [codeResendSeconds])

  function changeMode(nextMode: Mode) {
    setMode(nextMode)
    setCodeConfirmation(null)
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

  function requestCodeConfirmation() {
    if (codeResendSeconds > 0) return
    const normalizedEmail = email.trim()
    if (!normalizedEmail || !normalizedEmail.includes('@')) {
      setError('请先输入有效的邮箱地址。')
      return
    }
    if (mode === 'login') return
    setError('')
    setNotice('')
    setCodeConfirmation({ email: normalizedEmail, mode })
  }

  async function confirmSendCode() {
    if (!codeConfirmation || codeSendingRef.current) return
    codeSendingRef.current = true
    setCodeSending(true)
    setError('')
    setNotice('')
    try {
      if (codeConfirmation.mode === 'register') {
        await requestRegistrationCode(codeConfirmation.email)
      } else {
        await requestPasswordResetCode(codeConfirmation.email)
      }
      setCodeResendSeconds(CODE_RESEND_SECONDS)
      setNotice('验证码已发送，请查收邮件。')
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '验证码发送失败，请稍后重试。')
    } finally {
      codeSendingRef.current = false
      setCodeSending(false)
      setCodeConfirmation(null)
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
            <h2 id="welcome-title">你好，{user.display_name}</h2>
            <p className="account-meta">{accountMeta(user)}</p>
          </div>
          <button className="button button--secondary" onClick={handleLogout} disabled={submitting}>
            退出登录
          </button>
          {error && <p className="form-error">{error}</p>}
        </section>
        {user.roles.some((role) => role === 'teacher' || role === 'administrator') ? (
          <TeacherWorkspace isAdministrator={user.roles.includes('administrator')} />
        ) : (
          <StudentAssignments />
        )}
      </div>
    )
  }

  return (
    <section className="auth-card" aria-label="账号认证">
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
                  {classGroup.name}
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
                disabled={codeSending || codeConfirmation !== null || codeResendSeconds > 0}
                onClick={requestCodeConfirmation}
              >
                {codeSending
                  ? '发送中…'
                  : codeResendSeconds > 0
                    ? `${codeResendSeconds} 秒后重试`
                    : '获取验证码'}
              </button>
            </span>
          </label>
        )}
        <PasswordField
          key={mode}
          label={mode === 'forgot_password' ? '新密码' : '密码'}
          name="password"
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
        />
        {mode !== 'login' && (
          <PasswordField
            label="确认密码"
            name="password_confirmation"
            autoComplete="new-password"
          />
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
      {codeConfirmation && (
        <div className="confirmation-overlay">
          <section
            className="confirmation-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="email-confirmation-title"
            aria-describedby="email-confirmation-description"
            onKeyDown={(event) => {
              if (event.key === 'Escape' && !codeSending) setCodeConfirmation(null)
            }}
          >
            <h2 id="email-confirmation-title">确认邮箱地址</h2>
            <p id="email-confirmation-description">验证码将发送至：</p>
            <strong className="confirmation-dialog__email">{codeConfirmation.email}</strong>
            <p className="confirmation-dialog__hint">请确认邮箱地址填写正确。</p>
            <div className="confirmation-dialog__actions">
              <button
                className="button button--secondary"
                type="button"
                disabled={codeSending}
                onClick={() => setCodeConfirmation(null)}
              >
                取消
              </button>
              <button
                className="button"
                type="button"
                disabled={codeSending}
                onClick={() => void confirmSendCode()}
                autoFocus
              >
                {codeSending ? '发送中…' : '确认发送'}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  )
}
