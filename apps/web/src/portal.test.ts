import { describe, expect, it } from 'vitest'

import { portalHome, resolvePortal } from './portal'

describe('portal configuration', () => {
  it('uses an explicit production build role before the browser port', () => {
    expect(resolvePortal({
      configuredPortal: 'teacher',
      mode: 'production',
      port: '5173',
    })).toBe('teacher')
    expect(resolvePortal({
      configuredPortal: 'student',
      mode: 'production',
      port: '5174',
    })).toBe('student')
  })

  it('uses port 5174 for the teacher development server', () => {
    expect(resolvePortal({ mode: 'development', port: '5173' })).toBe('student')
    expect(resolvePortal({ mode: 'development', port: '5174' })).toBe('teacher')
  })

  it('switches between development portals at their root origins', () => {
    const location = { href: 'http://localhost:5174/legacy/path?query=1#section' } as Location

    expect(portalHome('student', location)).toBe('http://localhost:5173/')
    expect(portalHome('teacher', location)).toBe('http://localhost:5174/')
  })
})
