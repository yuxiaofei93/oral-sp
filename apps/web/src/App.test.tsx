import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

describe('App', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    window.history.replaceState({}, '', '/')
  })

  it('shows the teaching boundary and ready API status', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.includes('/api/health/')) return Promise.resolve(new Response('{}', { status: 200 }))
      return Promise.resolve(new Response('{"detail":"not authenticated"}', { status: 403 }))
    })

    render(<App />)

    expect(screen.getByRole('heading', { name: '口腔门诊 AI 模拟问诊系统' })).toBeInTheDocument()
    expect(screen.getByText('仅用于教学模拟，不用于真实患者诊疗。')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('服务已就绪'))
    expect(screen.getByRole('link', { name: /学生入口/ })).toHaveAttribute('href', '/student/')
    expect(screen.getByRole('link', { name: /教师入口/ })).toHaveAttribute('href', '/teacher/')
  })

  it('reports an unavailable API without crashing', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.includes('/api/health/')) return Promise.reject(new Error('network unavailable'))
      return Promise.resolve(new Response('{"detail":"not authenticated"}', { status: 403 }))
    })

    render(<App />)

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('服务暂不可用'))
  })

  it('renders independent student and teacher login pages', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.includes('/api/health/')) return Promise.resolve(new Response('{}', { status: 200 }))
      return Promise.resolve(new Response('{"detail":"not authenticated"}', { status: 403 }))
    })

    window.history.replaceState({}, '', '/teacher/')
    const { unmount } = render(<App />)
    expect(screen.getByRole('heading', { name: '教师教学入口' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('heading', { name: '教师登录' })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: '学生注册' })).not.toBeInTheDocument()

    unmount()
    window.history.replaceState({}, '', '/student/')
    render(<App />)
    expect(screen.getByRole('heading', { name: '学生学习入口' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('heading', { name: '学生登录' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '学生注册' })).toBeInTheDocument()
  })
})
