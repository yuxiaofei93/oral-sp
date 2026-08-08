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
  specialty: '',
  disease_tags: [],
  difficulty: 'intermediate',
  estimated_minutes: 20,
  teaching_objectives: '',
  target_grade: '',
  is_exam_mode: true,
  time_limit_minutes: 20,
  enabled_stages: ['interview'],
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

  it('saves a step with optimistic locking and supports adding facts', async () => {
    const savedBodies: Array<Record<string, unknown>> = []
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"case-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/draft/')) {
        savedBodies.push(JSON.parse(String(init?.body)))
        expect(init?.method).toBe('PATCH')
        expect(init?.headers).toMatchObject({ 'X-CSRFToken': 'case-csrf' })
        expect(String(init?.body)).toContain('expected_updated_at')
        return Promise.resolve(
          new Response(
            JSON.stringify({ ...draft, updated_at: '2026-08-04T00:01:00Z' }),
            { status: 200 },
          ),
        )
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<CaseEditor initialDraft={draft} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '保存并继续' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '患者身份与表达方式' })).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: /患者事实/ }))
    fireEvent.click(screen.getByRole('button', { name: '添加事实信息点' }))
    expect(screen.getByText('信息点 1')).toBeInTheDocument()
    const tagInput = screen.getByLabelText('语义路由提示词（可选，逗号分隔）')
    fireEvent.change(tagInput, { target: { value: '多久' } })
    fireEvent.change(tagInput, { target: { value: '多久，' } })
    expect(tagInput).toHaveValue('多久，')
    fireEvent.change(tagInput, { target: { value: '多久，病程；多长时间' } })
    fireEvent.blur(tagInput)
    expect(tagInput).toHaveValue('多久，病程，多长时间')
    fireEvent.click(screen.getByRole('button', { name: '保存并继续' }))
    await waitFor(() => expect(savedBodies).toHaveLength(2))
    expect(savedBodies[1]).toMatchObject({
      facts: [{ semantic_tags: ['多久', '病程', '多长时间'] }],
    })
  })
})
