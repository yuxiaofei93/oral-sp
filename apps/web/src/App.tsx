import { useEffect, useState } from 'react'

import { AuthPanel } from './auth/AuthPanel'

type ApiStatus = 'checking' | 'ready' | 'unavailable'

export function App() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')

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

  return (
    <main className="shell">
      <section className="hero" aria-labelledby="product-title">
        <p className="eyebrow">AI STANDARDIZED PATIENT</p>
        <h1 id="product-title">口腔门诊 AI 模拟问诊系统</h1>
        <p className="summary">
          面向口腔医学教学的结构化病例、分阶段问诊与可追溯评分平台。
        </p>
        <div className={`status status--${apiStatus}`} role="status">
          <span aria-hidden="true" />
          {statusText}
        </div>
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

      <AuthPanel />

      <p className="disclaimer">仅用于教学模拟，不用于真实患者诊疗。</p>
    </main>
  )
}
