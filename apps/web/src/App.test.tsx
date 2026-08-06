import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

describe('App', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    window.history.replaceState({}, '', '/')
  })

  it('uses the student homepage at the root address', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{"detail":"not authenticated"}', { status: 403 }),
    )

    render(<App />)

    expect(screen.getByRole('heading', { name: '口腔门诊模拟问诊系统' })).toBeInTheDocument()
    expect(screen.getByText('面向口腔医学教学的模拟患者问诊与临床思维训练平台。')).toBeInTheDocument()
    expect(screen.getByText('仅用于教学模拟，不用于真实患者诊疗。')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('heading', { name: '学生登录' })).toBeInTheDocument())
    expect(screen.queryByText('STUDENT PORTAL')).not.toBeInTheDocument()
    expect(screen.queryByText('服务已就绪')).not.toBeInTheDocument()
    expect(screen.queryByText('选择您的入口')).not.toBeInTheDocument()
  })

  it('renders the page when the account service is unavailable', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/me/')) return Promise.reject(new Error('network unavailable'))
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<App />)

    expect(screen.getByRole('heading', { name: '口腔门诊模拟问诊系统' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('暂时无法读取登录状态。')).toBeInTheDocument())
  })

  it('renders an independent teacher login page', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{"detail":"not authenticated"}', { status: 403 }),
    )

    window.history.replaceState({}, '', '/teacher/')
    const { unmount } = render(<App />)
    expect(screen.getByRole('heading', { name: '教师教学工作台' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('heading', { name: '教师登录' })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: '学生注册' })).not.toBeInTheDocument()
    unmount()
  })
})
