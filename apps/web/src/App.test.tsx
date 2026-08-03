import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

describe('App', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
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
    await waitFor(() => expect(screen.getByRole('heading', { name: '进入教学平台' })).toBeInTheDocument())
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
})
