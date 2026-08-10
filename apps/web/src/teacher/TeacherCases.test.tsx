import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TeacherCases } from './TeacherCases'

const createdDraft = {
  id: 'draft-1',
  case_id: 'case-1',
  case_code: 'CASE-000001',
  status: 'draft',
  version_number: null,
  title_internal: '未命名病例',
  difficulty: 'intermediate',
  is_exam_mode: true,
  time_limit_minutes: 20,
  enabled_stages: ['interview'],
  patient_prompt_mode: 'default',
  patient_prompt: '',
  effective_patient_prompt: '默认患者问诊提示词。',
  default_patient_prompt: '默认患者问诊提示词。',
  created_at: '2026-08-08T00:00:00Z',
  updated_at: '2026-08-08T00:00:00Z',
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

describe('TeacherCases', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('creates an unnamed draft and enters basic information immediately', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/teacher/cases/') && !init?.method) {
        return Promise.resolve(new Response(JSON.stringify([{
          id: 'case-1',
          code: 'CASE-000001',
          is_active: true,
          created_at: '2026-08-08T00:00:00Z',
          draft: {
            id: 'draft-1',
            title_internal: '牙龈疼痛病例',
            updated_at: '2026-08-08T00:00:00Z',
          },
          latest_published: null,
        }]), { status: 200 }))
      }
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"case-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/teacher/cases/') && init?.method === 'POST') {
        expect(init.body).toBe('{}')
        return Promise.resolve(new Response(JSON.stringify(createdDraft), { status: 201 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<TeacherCases />)
    expect(await screen.findByRole('heading', { name: '病例库' })).toBeInTheDocument()
    expect(screen.queryByText('TEACHER WORKSPACE')).not.toBeInTheDocument()
    expect(screen.queryByText('用标准表单维护病例事实、检查、诊断和评分规则，不需要编写提示词。')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '编辑病例' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑草稿' })).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '新建病例' }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '基础信息' })).toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { name: '未命名病例' })).toBeInTheDocument()
  })

  it('returns to and refreshes the case list after publishing', async () => {
    let listRequests = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/teacher/cases/') && !init?.method) {
        listRequests += 1
        return Promise.resolve(new Response(JSON.stringify([{
          id: 'case-1',
          code: 'CASE-000001',
          is_active: true,
          created_at: '2026-08-08T00:00:00Z',
          draft: {
            id: 'draft-1',
            title_internal: '未命名病例',
            updated_at: '2026-08-08T00:00:00Z',
          },
          latest_published: listRequests > 1 ? {
            id: 'version-1',
            version_number: 1,
            published_at: '2026-08-08T00:01:00Z',
          } : null,
        }]), { status: 200 }))
      }
      if (url.endsWith('/teacher/cases/case-1/draft/')) {
        return Promise.resolve(new Response(JSON.stringify(createdDraft), { status: 200 }))
      }
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"case-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/teacher/cases/case-1/publish/')) {
        expect(init?.method).toBe('POST')
        return Promise.resolve(new Response(JSON.stringify({
          created: true,
          version: {
            id: 'version-1',
            version_number: 1,
            published_at: '2026-08-08T00:01:00Z',
            content_hash: 'hash',
          },
        }), { status: 201 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<TeacherCases />)
    fireEvent.click(await screen.findByRole('button', { name: '编辑病例' }))
    fireEvent.click(await screen.findByRole('button', { name: '发布病例' }))

    expect(await screen.findByRole('heading', { name: '病例库' })).toBeInTheDocument()
    expect(await screen.findByText('已发布 v1')).toBeInTheDocument()
    expect(listRequests).toBe(2)
  })
})
