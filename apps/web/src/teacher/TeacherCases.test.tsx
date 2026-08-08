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

  it('creates an unnamed draft and enters teaching settings immediately', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/teacher/cases/') && !init?.method) {
        return Promise.resolve(new Response('[]', { status: 200 }))
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
    fireEvent.click(await screen.findByRole('button', { name: '新建病例' }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '教学设置' })).toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { name: '未命名病例' })).toBeInTheDocument()
  })
})
