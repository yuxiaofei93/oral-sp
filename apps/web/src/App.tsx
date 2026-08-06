import { AuthPanel } from './auth/AuthPanel'

type Portal = 'student' | 'teacher'

function currentPortal(pathname: string): Portal {
  const normalizedPath = pathname.replace(/\/+$/, '') || '/'
  if (normalizedPath === '/teacher') return 'teacher'
  return 'student'
}

export function App() {
  const portal = currentPortal(window.location.pathname)

  const portalCopy = portal === 'student'
    ? {
        title: '口腔门诊模拟问诊系统',
        summary: '面向口腔医学教学的模拟患者问诊与临床思维训练平台。',
      }
    : {
        title: '教师教学工作台',
        summary: '口腔医学模拟问诊的病例、班级与教学任务管理平台。',
      }

  return (
    <main className={`shell shell--portal shell--${portal}`}>
      <header className="portal-header" aria-labelledby="portal-title">
        <h1 id="portal-title">{portalCopy.title}</h1>
        <p className="summary">{portalCopy.summary}</p>
      </header>

      <AuthPanel portal={portal} />

      <p className="disclaimer">仅用于教学模拟，不用于真实患者诊疗。</p>
    </main>
  )
}
