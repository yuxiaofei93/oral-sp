import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TeacherAssignment } from '../api/client'
import { TeacherResponses } from './TeacherResponses'

const assignment: TeacherAssignment = {
  id: 'assignment-1',
  title: '牙周问诊考试',
  case_version_id: 'version-1',
  class_group_id: 'class-1',
  case_title: '牙周病例',
  case_version_number: 1,
  course_name: '口腔问诊训练',
  class_name: 'A 班',
  duration_minutes: 20,
  opens_at: '2026-08-04T00:00:00Z',
  deadline_at: '2026-08-04T01:00:00Z',
  status: 'closed',
  feedback_released_at: null,
  student_count: 1,
  not_started_count: 0,
  active_count: 0,
  submitted_count: 1,
  expired_count: 0,
  created_at: '2026-08-04T00:00:00Z',
}

describe('TeacherResponses', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows a student record with automatic score and traceable evidence', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/assignment-1/responses/')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                student_id: 'student-1',
                display_name: '学生甲',
                phone: '+8613800138000',
                attempt_status: 'completed',
                session_id: 'session-1',
                started_at: '2026-08-04T00:00:00Z',
                completed_at: '2026-08-04T00:10:00Z',
                elapsed_seconds: 600,
                score: { automatic_score: 8, scored_maximum: 8, maximum_score: 9, provisional: true },
              },
            ]),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/session-1/record/')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 'session-1',
              assignment_id: 'assignment-1',
              assignment_title: '牙周问诊考试',
              case_title: '牙周病例',
              patient_name: '陈女士',
              opening_statement: '医生您好。',
              status: 'completed',
              stage: 'completed',
              started_at: '2026-08-04T00:00:00Z',
              deadline_at: '2026-08-04T00:20:00Z',
              completed_at: '2026-08-04T00:10:00Z',
              remaining_seconds: 0,
              student_id: 'student-1',
              student_name: '学生甲',
              student_phone: '+8613800138000',
              messages: [
                { id: 'm1', sequence: 1, role: 'student', content: '疼了多久？' },
                { id: 'm2', sequence: 2, role: 'patient', content: '三年了。' },
              ],
              submissions: [],
              assessment: {
                automatic_score: 8,
                scored_maximum: 8,
                maximum_score: 9,
                provisional: true,
                omissions: [],
                errors: [],
                feedback_summary: '自动规则评分覆盖 4 个评分项。',
                ai_feedback: '',
                scoring_version: 'rules-v1',
                generated_at: '2026-08-04T00:10:00Z',
                scoring_items: [
                  {
                    code: 'fact:duration',
                    label: '病程三年',
                    dimension: 'history',
                    automatic_score: 2,
                    max_score: 2,
                    decision: 'achieved',
                    evidence_excerpt: '学生：疼了多久？\n患者：三年了。',
                    standard_answer: '病程三年',
                    reason: '已覆盖事实点。',
                  },
                ],
              },
              standard_diagnoses: [{ type: 'final', name: '慢性牙周炎', supporting_evidence: ['病程长'] }],
              standard_tests: [],
            }),
            { status: 200 },
          ),
        )
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<TeacherResponses assignment={assignment} onClose={vi.fn()} />)
    await waitFor(() => screen.getByText('学生甲'))
    fireEvent.click(screen.getByRole('button', { name: '查看答卷' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: '学生甲的答卷' })).toBeInTheDocument())
    expect(screen.getByText(/学生：疼了多久/)).toBeInTheDocument()
    expect(screen.getByText(/慢性牙周炎/)).toBeInTheDocument()
  })
})
