export type Portal = 'student' | 'teacher'

const DEFAULT_STUDENT_PORT = '5173'
const DEFAULT_TEACHER_PORT = '5174'

export function resolvePortal({
  configuredPortal,
  mode,
  port,
}: {
  configuredPortal?: string
  mode?: string
  port: string
}): Portal {
  if (configuredPortal === 'student' || configuredPortal === 'teacher') {
    return configuredPortal
  }
  if (mode === 'teacher' || port === DEFAULT_TEACHER_PORT) return 'teacher'
  return 'student'
}

function normalizedOrigin(value: string | undefined): string | null {
  const origin = value?.trim().replace(/\/+$/, '')
  return origin ? `${origin}/` : null
}

export function portalHome(portal: Portal, location: Location = window.location): string {
  const configuredOrigin = normalizedOrigin(
    portal === 'student'
      ? import.meta.env.VITE_STUDENT_ORIGIN
      : import.meta.env.VITE_TEACHER_ORIGIN,
  )
  if (configuredOrigin) return configuredOrigin

  const url = new URL(location.href)
  url.pathname = '/'
  url.search = ''
  url.hash = ''
  url.port = portal === 'student' ? DEFAULT_STUDENT_PORT : DEFAULT_TEACHER_PORT
  return url.toString()
}
