import { useEffect, useState } from 'react'

import { AuthPanel } from './auth/AuthPanel'

type ApiStatus = 'checking' | 'ready' | 'unavailable'
type Portal = 'student' | 'teacher'

function currentPortal(pathname: string): Portal {
  const normalizedPath = pathname.replace(/\/+$/, '') || '/'
  if (normalizedPath === '/teacher') return 'teacher'
  return 'student'
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
