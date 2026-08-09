import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PatientPromptTemplateEditor } from './PatientPromptTemplateEditor'

const template = {
  id: 1,
  name: '默认患者问诊模板',
  content: '请用自然口语回答口腔问诊问题。',
  updated_by_name: '',
  updated_at: '2026-08-08T00:00:00Z',
}

const questionTemplate = {
  id: 1,
  name: '默认患者主动提问',
  questions: [{
    id: 'diagnosis',
    base_question: '医生，我这是个什么病？',
    answer_criteria: '给出诊断或说明判断下一步。',
    enabled: true,
  }],
  updated_by_name: '',
  updated_at: '2026-08-08T00:00:00Z',
}

describe('PatientPromptTemplateEditor', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('loads and saves the shared default patient prompt', async () => {
    let savedBody: Record<string, unknown> | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/patient-prompt-template/') && !init?.method) {
        return Promise.resolve(new Response(JSON.stringify(template), { status: 200 }))
      }
      if (url.endsWith('/patient-question-template/') && !init?.method) {
        return Promise.resolve(new Response(JSON.stringify(questionTemplate), { status: 200 }))
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
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<PatientPromptTemplateEditor />)

    const promptInput = await screen.findByLabelText('默认患者问诊提示词')
    expect(screen.getByRole('heading', { level: 2, name: '系统设置' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: '默认患者问诊模板' })).toBeInTheDocument()
    expect(promptInput).toHaveValue(template.content)
    expect(screen.queryByText('所有选择默认模板的病例草稿都会使用这里的内容。')).not.toBeInTheDocument()
    expect(screen.getByText(/已发布病例保存的是发布当时的提示词/)).toBeInTheDocument()

    fireEvent.change(promptInput, { target: { value: '请保持耐心，并用简短口语回答。' } })
    fireEvent.click(screen.getByRole('button', { name: '保存默认模板' }))

    await waitFor(() => expect(savedBody).toEqual({
      content: '请保持耐心，并用简短口语回答。',
    }))
    expect(await screen.findByText('默认提示词已保存。')).toBeInTheDocument()
    expect(screen.getByText('最近由 测试教师 更新')).toBeInTheDocument()
  })

  it('lets an administrator maintain the shared patient question list', async () => {
    let savedQuestions: unknown = null
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/patient-prompt-template/') && !init?.method) {
        return Promise.resolve(new Response(JSON.stringify(template), { status: 200 }))
      }
      if (url.endsWith('/patient-question-template/') && !init?.method) {
        return Promise.resolve(new Response(JSON.stringify(questionTemplate), { status: 200 }))
      }
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"question-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/patient-question-template/') && init?.method === 'PATCH') {
        const body = JSON.parse(String(init.body)) as { questions: unknown }
        savedQuestions = body.questions
        return Promise.resolve(new Response(JSON.stringify({
          ...questionTemplate,
          questions: body.questions,
          updated_by_name: '系统管理员',
        }), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<PatientPromptTemplateEditor isAdministrator />)
    const questionInput = await screen.findByDisplayValue('医生，我这是个什么病？')
    fireEvent.change(questionInput, { target: { value: '医生，我得的是什么病？' } })
    fireEvent.click(screen.getByRole('button', { name: '保存默认主动问题' }))

    await waitFor(() => expect(savedQuestions).toEqual([{
      ...questionTemplate.questions[0],
      base_question: '医生，我得的是什么病？',
    }]))
    expect(await screen.findByText('默认主动问题已保存。')).toBeInTheDocument()
  })
})
