import { useEffect } from 'react'

import { AuthPanel } from './auth/AuthPanel'
import type { Portal } from './portal'
import { resolvePortal } from './portal'

export function PortalApp({ portal }: { portal: Portal }) {
  const portalCopy = portal === 'student'
    ? {
        title: '口腔门诊模拟问诊系统',
      }
    : {
        title: '口腔模拟问诊系统管理后台',
      }

  return (
    <main className={`shell shell--portal shell--${portal}`}>
      <header className="portal-header" aria-labelledby="portal-title">
        <h1 id="portal-title">{portalCopy.title}</h1>
      </header>

      <AuthPanel portal={portal} />
    </main>
  )
}

export function App() {
  const portal = resolvePortal({
    configuredPortal: import.meta.env.VITE_PORTAL,
    mode: import.meta.env.MODE,
    port: window.location.port,
  })
  useEffect(() => {
    if (window.location.pathname !== '/') {
      window.history.replaceState({}, '', '/')
    }
  }, [])
  return <PortalApp portal={portal} />
}
