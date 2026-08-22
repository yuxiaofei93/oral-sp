import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PatientPromptTemplateEditor } from './PatientPromptTemplateEditor'

const template = {
  id: 1,
  name: '默认患者表达风格',
  content: '请用自然口语回答口腔问诊问题。',
  updated_by_name: '',
  updated_at: '2026-08-08T00:00:00Z',
}

const followUpTemplate = {
  id: 1,
  name: '默认体格检查后患者主动询问',
  questions: ['医生，我这个是什么病啊？', '那接下来要怎么治疗呢？'],
  closing_text: '好的，我明白了，谢谢医生。',
  updated_by_name: '',
  updated_at: '2026-08-08T00:00:00Z',
}

describe('PatientPromptTemplateEditor', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('loads and saves the shared default patient style', async () => {
    let savedBody: Record<string, unknown> | null = null
    let savedFollowUpBody: Record<string, unknown> | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/patient-prompt-template/') && !init?.method) {
        return Promise.resolve(new Response(JSON.stringify(template), { status: 200 }))
      }
      if (url.endsWith('/patient-follow-up-template/') && !init?.method) {
        return Promise.resolve(new Response(JSON.stringify(followUpTemplate), { status: 200 }))
      }
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"prompt-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/patient-prompt-template/') && init?.method === 'PATCH') {
        savedBody = JSON.parse(String(init.body)) as Record<string, unknown>
        return Promise.resolve(new Response(JSON.stringify({
          ...template,
          ...savedBody,
          updated_by_name: '测试教师',
          updated_at: '2026-08-08T00:01:00Z',
        }), { status: 200 }))
      }
      if (url.endsWith('/patient-follow-up-template/') && init?.method === 'PATCH') {
        savedFollowUpBody = JSON.parse(String(init.body)) as Record<string, unknown>
        return Promise.resolve(new Response(JSON.stringify({
          ...followUpTemplate,
          ...savedFollowUpBody,
          updated_by_name: '测试教师',
          updated_at: '2026-08-08T00:01:00Z',
        }), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<PatientPromptTemplateEditor />)

    const promptInput = await screen.findByLabelText('默认患者表达风格')
    expect(screen.getByRole('heading', { level: 2, name: '系统设置' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: '默认患者表达风格' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: '默认体格检查后患者主动询问' })).toBeInTheDocument()
    expect(promptInput).toHaveValue(template.content)
    expect(screen.queryByText('所有选择默认模板的病例草稿都会使用这里的内容。')).not.toBeInTheDocument()
    expect(screen.getByText(/事实边界、安全规则和输出格式由系统固定管理/)).toBeInTheDocument()
    expect(screen.getByText(/已发布病例保存的是发布当时的表达风格/)).toBeInTheDocument()

    fireEvent.change(promptInput, { target: { value: '请保持耐心，并用简短口语回答。' } })
    fireEvent.click(screen.getByRole('button', { name: '保存默认风格' }))

    await waitFor(() => expect(savedBody).toEqual({
      content: '请保持耐心，并用简短口语回答。',
    }))
    expect(await screen.findByText('默认表达风格已保存。')).toBeInTheDocument()
    expect(screen.getByText('最近由 测试教师 更新')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('主动询问 1'), {
      target: { value: '医生，这是什么问题？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '添加主动询问' }))
    fireEvent.change(screen.getByLabelText('主动询问 3'), {
      target: { value: '平时需要注意什么？' },
    })
    fireEvent.change(screen.getByLabelText('默认主动问答收尾语'), {
      target: { value: '好的，谢谢。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存默认主动问答' }))

    await waitFor(() => expect(savedFollowUpBody).toEqual({
      questions: ['医生，这是什么问题？', '那接下来要怎么治疗呢？', '平时需要注意什么？'],
      closing_text: '好的，谢谢。',
    }))
    expect(await screen.findByText('默认患者主动问答已保存。')).toBeInTheDocument()
  })
})
