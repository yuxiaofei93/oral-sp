import { useEffect, useState } from 'react'

import { AuthPanel } from './auth/AuthPanel'

type ApiStatus = 'checking' | 'ready' | 'unavailable'
type Portal = 'student' | 'teacher'

function currentPortal(pathname: string): Portal | null {
  const normalizedPath = pathname.replace(/\/+$/, '') || '/'
  if (normalizedPath === '/student') return 'student'
  if (normalizedPath === '/teacher') return 'teacher'
  return null
}

export function App() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')
  const portal = currentPortal(window.location.pathname)

  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/health/ready/', { signal: controller.signal })
      .then((response) => {
        setApiStatus(response.ok ? 'ready' : 'unavailable')
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setApiStatus('unavailable')
      })

    return () => controller.abort()
  }, [])

  const statusText = {
    checking: '正在检查服务状态',
    ready: '服务已就绪',
    unavailable: '服务暂不可用',
  }[apiStatus]

  const serviceStatus = (
    <div className={`status status--${apiStatus}`} role="status">
      <span aria-hidden="true" />
      {statusText}
    </div>
  )

  if (portal) {
    const portalCopy = portal === 'student'
      ? {
          eyebrow: 'STUDENT PORTAL',
          title: '学生学习入口',
          summary: '完成教师发布的模拟问诊任务，并在统一发布后查看反馈。',
        }
      : {
          eyebrow: 'TEACHER PORTAL',
          title: '教师教学入口',
          summary: '管理病例、班级和考试任务，查看答卷并发布教学反馈。',
        }

    return (
      <main className={`shell shell--portal shell--${portal}`}>
        <header className="portal-header" aria-labelledby="portal-title">
          <a className="back-link" href="/">← 返回入口选择</a>
          <p className="eyebrow">{portalCopy.eyebrow}</p>
          <h1 id="portal-title">{portalCopy.title}</h1>
          <p className="summary">{portalCopy.summary}</p>
          {serviceStatus}
        </header>

        <AuthPanel portal={portal} />

        <p className="disclaimer">仅用于教学模拟，不用于真实患者诊疗。</p>
      </main>
    )
  }

  return (
    <main className="shell">
      <section className="hero" aria-labelledby="product-title">
        <p className="eyebrow">AI STANDARDIZED PATIENT</p>
        <h1 id="product-title">口腔门诊 AI 模拟问诊系统</h1>
        <p className="summary">
          面向口腔医学教学的结构化病例、分阶段问诊与可追溯评分平台。
        </p>
        {serviceStatus}
      </section>

      <section className="principles" aria-label="产品原则">
        <article>
          <strong>病例一致</strong>
          <span>患者只回答病例定义的事实</span>
        </article>
        <article>
          <strong>过程留痕</strong>
          <span>消息、提交和检查申请不可覆盖</span>
        </article>
        <article>
          <strong>教学可控</strong>
          <span>教师统一发布反馈和标准答案</span>
        </article>
      </section>

      <section className="portal-choices" aria-labelledby="portal-choice-title">
        <div className="section-heading">
          <p className="eyebrow">CHOOSE YOUR PORTAL</p>
          <h2 id="portal-choice-title">选择您的入口</h2>
        </div>
        <div className="portal-choices__grid">
          <a className="portal-choice portal-choice--student" href="/student/">
            <span className="portal-choice__number">01</span>
            <strong>学生入口</strong>
            <p>注册学生账号、参加问诊练习并查看已发布的反馈。</p>
            <span className="portal-choice__action">进入学生端 →</span>
          </a>
          <a className="portal-choice portal-choice--teacher" href="/teacher/">
            <span className="portal-choice__number">02</span>
            <strong>教师入口</strong>
            <p>使用已授权的教师账号管理病例、班级和考试任务。</p>
            <span className="portal-choice__action">进入教师端 →</span>
          </a>
        </div>
      </section>

      <p className="disclaimer">仅用于教学模拟，不用于真实患者诊疗。</p>
    </main>
  )
}
