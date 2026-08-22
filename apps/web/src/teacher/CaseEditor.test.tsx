import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CaseDraft } from '../api/client'
import { CaseEditor } from './CaseEditor'

const draft: CaseDraft = {
  id: 'draft-1',
  case_id: 'case-1',
  case_code: 'OM-001',
  status: 'draft',
  version_number: null,
  title_internal: '牙龈疼痛教学病例',
  difficulty: 'intermediate',
  is_exam_mode: true,
  time_limit_minutes: 20,
  enabled_stages: ['interview'],
  patient_prompt_mode: 'default',
  patient_prompt: '',
  effective_patient_prompt: '默认患者表达风格。',
  default_patient_prompt: '默认患者表达风格。',
  created_at: '2026-08-04T00:00:00Z',
  updated_at: '2026-08-04T00:00:00Z',
  patient_profile: {
    display_name: '',
    age: null,
    sex: 'unspecified',
    occupation: '',
    education: '',
    personality: '',
    emotion: '',
    cooperation: '',
    medical_literacy: '',
    opening_statement: '',
    avatar_asset_id: '',
    voice_id: '',
  },
  physical_exam: {
    findings_text: '',
    consent_text: '可以，麻烦您检查吧。',
    images: [],
    attachments: [],
  },
  facts: [],
  tests: [],
  diagnosis_rules: [],
  scoring_items: [],
}

describe('CaseEditor', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows every section and automatically saves the complete draft with optimistic locking', async () => {
    const savedBodies: Array<Record<string, unknown>> = []
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"case-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/draft/')) {
        const body = JSON.parse(String(init?.body)) as Record<string, unknown>
        savedBodies.push(body)
        expect(init?.method).toBe('PATCH')
        expect(init?.headers).toMatchObject({ 'X-CSRFToken': 'case-csrf' })
        expect(String(init?.body)).toContain('expected_updated_at')
        const savedFacts = (body.facts as Array<Record<string, unknown>>).map((fact, index) => ({
          ...fact,
          id: index + 100,
        }))
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...draft,
              ...body,
              facts: savedFacts,
              updated_at: '2026-08-04T00:01:00Z',
            }),
            { status: 200 },
          ),
        )
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<CaseEditor initialDraft={draft} onClose={vi.fn()} />)
    expect(savedBodies).toHaveLength(0)
    expect(screen.getByText('已自动保存')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '基础信息' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'AI 患者表达风格' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '教学设置' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '患者身份与表达方式' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '患者信息 [0点]' })).toBeInTheDocument()
    expect(screen.queryByText('每个事实都是独立信息点。AI 只能围绕这些事实回答，未定义内容不得补齐。')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '口腔体格检查' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '辅助检查资料（0）' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '诊断规则（0）' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '评分规则（0）' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '发布前检查' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /基础信息/ })).toHaveAttribute('href', '#basic-info')
    expect(screen.getByRole('link', { name: /患者表达风格/ })).toHaveAttribute('href', '#patient-prompt')
    expect(screen.getByRole('link', { name: /病情信息/ })).toHaveAttribute('href', '#patient-facts')
    expect(screen.getByRole('link', { name: /口腔体格检查/ })).toHaveAttribute('href', '#physical-exam')
    expect(screen.queryByRole('button', { name: '保存并继续' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '保存全部修改' })).not.toBeInTheDocument()
    const publishButton = screen.getByRole('button', { name: '发布病例' })
    expect(publishButton.closest('.case-editor__header')).not.toBeNull()
    expect(screen.queryByLabelText('难度')).not.toBeInTheDocument()
    expect(screen.getByLabelText('化名')).toBeInTheDocument()
    expect(screen.queryByLabelText('性格与配合程度')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('当前情绪')).not.toBeInTheDocument()
    expect(screen.getByLabelText('患者开场白(必填)')).toBeInTheDocument()
    expect(screen.getByLabelText('表达风格来源')).toHaveValue('default')
    expect(screen.getByLabelText('患者表达风格')).toHaveValue('默认患者表达风格。')
    expect(screen.getByLabelText('患者表达风格')).toHaveAttribute('readonly')

    fireEvent.change(screen.getByLabelText('表达风格来源'), { target: { value: 'custom' } })
    expect(screen.getByLabelText('患者表达风格')).not.toHaveAttribute('readonly')
    fireEvent.change(screen.getByLabelText('患者表达风格'), {
      target: { value: '请让患者回答得更简短。' },
    })

    fireEvent.click(screen.getByRole('button', { name: '添加事实信息点' }))
    expect(screen.getByRole('heading', { name: '患者信息 [1点]' })).toBeInTheDocument()
    expect(screen.getByText('信息点 1')).toBeInTheDocument()
    expect(screen.queryByLabelText('信息点编码')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('标准事实')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('患者口语表达')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('分类')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('病例未提供时的回答')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('事实点分值')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('必问信息点')).not.toBeInTheDocument()
    expect(screen.getByText('填写患者病情相关信息，AI 会在问诊中以患者口吻自然表达。')).toBeInTheDocument()
    const factContentInput = screen.getByLabelText('内容')
    fireEvent.change(factContentInput, { target: { value: '病程约三年' } })
    factContentInput.focus()
    expect(screen.queryByLabelText('语义路由提示词（可选，逗号分隔）')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('典型同义问法（可选，逗号分隔）')).not.toBeInTheDocument()
    await waitFor(() => expect(savedBodies).toHaveLength(1), { timeout: 2000 })
    await waitFor(() => expect(screen.getByText('已自动保存')).toBeInTheDocument())
    expect(screen.getByLabelText('内容')).toBe(factContentInput)
    expect(factContentInput).toHaveFocus()
    expect(savedBodies[0]).toMatchObject({
      title_internal: '牙龈疼痛教学病例',
      patient_profile: draft.patient_profile,
      patient_prompt_mode: 'custom',
      patient_prompt: '请让患者回答得更简短。',
      facts: [{
        code: 'fact.1',
        standard_fact: '病程约三年',
        patient_expression: '病程约三年',
      }],
      tests: [],
      diagnosis_rules: [],
      scoring_items: [],
    })
    expect(savedBodies[0]).not.toHaveProperty('default_patient_prompt')
    expect(savedBodies[0]).not.toHaveProperty('effective_patient_prompt')
  })

  it('shows nested draft validation errors with section and item context', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"case-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/draft/')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              facts: [
                {
                  standard_fact: ['该字段不能为空。'],
                  patient_expression: ['该字段不能为空。'],
                },
              ],
              tests: [{ name: ['该字段不能为空。'] }],
            }),
            { status: 400 },
          ),
        )
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<CaseEditor initialDraft={draft} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '添加事实信息点' }))
    fireEvent.click(screen.getByRole('button', { name: '添加检查' }))

    expect(await screen.findByText(
      '病情信息 1 / 内容：该字段不能为空。；辅助检查资料 1 / 检查名称：该字段不能为空。',
      {},
      { timeout: 2000 },
    )).toBeInTheDocument()
    expect(screen.queryByText('请求失败，请稍后重试。')).not.toBeInTheDocument()
  })

  it('uploads a confirmed physical exam image and renders its private preview', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"case-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/physical-exam/assets/')) {
        expect(init?.method).toBe('POST')
        expect(init?.headers).toMatchObject({ 'X-CSRFToken': 'case-csrf' })
        const body = init?.body as FormData
        expect(body.get('kind')).toBe('image')
        expect(body.get('deidentified_confirmed')).toBe('true')
        return Promise.resolve(new Response(JSON.stringify({
          ...draft,
          updated_at: '2026-08-04T00:01:00Z',
          physical_exam: {
            ...draft.physical_exam,
            images: [{
              id: 1,
              kind: 'image',
              display_order: 0,
              filename: '口内照.jpg',
              content_type: 'image/jpeg',
              size_bytes: 2048,
              deidentified_confirmed: true,
              content_url: '/api/teacher/cases/case-1/draft/physical-exam/assets/1/content/',
            }],
          },
        }), { status: 201 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<CaseEditor initialDraft={draft} onClose={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('我确认上传资料已获授权并完成脱敏'))
    const file = new File(['image'], '口内照.jpg', { type: 'image/jpeg' })
    fireEvent.change(screen.getByLabelText('添加检查图片'), {
      target: { files: [file] },
    })

    expect(await screen.findByRole('img', { name: '口内照.jpg' })).toHaveAttribute(
      'src',
      '/api/teacher/cases/case-1/draft/physical-exam/assets/1/content/',
    )
  })

  it('saves pending changes before returning to the case list', async () => {
    const requestOrder: string[] = []
    const onClose = vi.fn(() => requestOrder.push('close'))
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"case-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/draft/')) {
        requestOrder.push('save')
        const body = JSON.parse(String(init?.body)) as Record<string, unknown>
        return Promise.resolve(new Response(JSON.stringify({
          ...draft,
          ...body,
          updated_at: '2026-08-04T00:01:00Z',
        }), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<CaseEditor initialDraft={draft} onClose={onClose} />)
    fireEvent.change(screen.getByLabelText('病例名称（仅教师可见）'), {
      target: { value: '返回前保存的病例' },
    })
    fireEvent.click(screen.getByRole('button', { name: '← 返回病例列表' }))

    await waitFor(() => expect(requestOrder).toEqual(['save', 'close']))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('saves all pending changes before publishing and returns to the case list', async () => {
    const requestOrder: string[] = []
    const onClose = vi.fn(() => requestOrder.push('close'))
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"case-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/draft/')) {
        requestOrder.push('save')
        const body = JSON.parse(String(init?.body)) as Record<string, unknown>
        expect(body.title_internal).toBe('更新后的病例名称')
        return Promise.resolve(
          new Response(
            JSON.stringify({ ...draft, ...body, updated_at: '2026-08-04T00:01:00Z' }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/publish/')) {
        requestOrder.push('publish')
        return Promise.resolve(new Response(JSON.stringify({
          created: true,
          version: {
            id: 'version-1',
            version_number: 1,
            published_at: '2026-08-04T00:02:00Z',
            content_hash: 'hash',
          },
        }), { status: 201 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<CaseEditor initialDraft={draft} onClose={onClose} />)
    fireEvent.change(screen.getByLabelText('病例名称（仅教师可见）'), {
      target: { value: '更新后的病例名称' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发布病例' }))

    await waitFor(() => expect(requestOrder).toEqual(['save', 'publish', 'close']))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
