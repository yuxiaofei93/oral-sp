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

  it('shows traceable evidence and submits a teacher review', async () => {
    let aiGenerated = false
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/api/auth/csrf/')) {
        return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'test-token' }), { status: 200 }))
      }
      if (url.endsWith('/session-1/reviews/')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 'review-1', revision: 1, reviewer_id: 'teacher-1', reviewer_name: '教师甲',
              score_overrides: { 'fact:duration': { score: '1.00', reason: '追问深度不足' } },
              comment: '继续加强追问', final_score: 7, scored_maximum: 8, maximum_score: 9,
              provisional: true, created_at: '2026-08-04T01:00:00Z',
            }),
            { status: 201 },
          ),
        )
      }
      if (url.endsWith('/session-1/ai-evaluation/')) {
        aiGenerated = true
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 'ai-run-1', status: 'succeeded', provider: 'deepseek', model: 'deepseek-v4-flash',
              requested_by_id: 'teacher-1', requested_by_name: '教师甲',
              resolved_model: 'DeepSeek-V4-Flash-0731', prompt_version: 'assessment-v1',
              scoring_item_codes: ['fact:duration'], feedback_summary: '提问简洁。', latency_ms: 320,
              input_tokens: 120, output_tokens: 80, error_code: '',
              created_at: '2026-08-04T00:20:00Z', completed_at: '2026-08-04T00:20:01Z', results: [],
            }),
            { status: 201 },
          ),
        )
      }
      if (url.endsWith('/assignment-1/statistics/')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              summary: {
                student_count: 1, started_count: 1, completed_count: 1, expired_count: 0,
                assessed_count: 1, completion_rate: 100, average_score: 8,
                average_score_percentage: 88.89, average_duration_seconds: 600,
              },
              frequent_omissions: [{ code: 'fact:site', label: '疼痛部位', count: 1, rate: 100 }],
              common_errors: [],
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/assignment-1/responses/')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                student_id: 'student-1',
                display_name: '学生甲',
                email: 'student@example.com',
                attempt_status: 'completed',
                session_id: 'session-1',
                started_at: '2026-08-04T00:00:00Z',
                completed_at: '2026-08-04T00:10:00Z',
                elapsed_seconds: 600,
                score: { automatic_score: 8, final_score: 8, scored_maximum: 8, maximum_score: 9, provisional: true },
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
              student_email: 'student@example.com',
              messages: [
                { id: 'm1', sequence: 1, role: 'student', content: '疼了多久？' },
                { id: 'm2', sequence: 2, role: 'patient', content: '三年了。' },
              ],
              submissions: [],
              assessment: {
                automatic_score: 8,
                final_score: aiGenerated ? 8.75 : 8,
                scored_maximum: aiGenerated ? 9 : 8,
                maximum_score: 9,
                provisional: !aiGenerated,
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
                    evaluation_method: 'ai',
                    automatic_score: null,
                    ai_score: aiGenerated ? 0.75 : null,
                    ai_confidence: aiGenerated ? 0.82 : null,
                    ai_reason: aiGenerated ? '提问围绕病程获取了有效信息。' : '',
                    ai_feedback: aiGenerated ? '可以先开放询问。' : '',
                    ai_evidence_excerpt: aiGenerated ? '学生：疼了多久？' : '',
                    teacher_score: null,
                    effective_score: aiGenerated ? 0.75 : null,
                    effective_decision: aiGenerated ? 'partial' : 'pending',
                    adjustment_reason: '',
                    max_score: 2,
                    decision: 'achieved',
                    evidence_excerpt: '学生：疼了多久？\n患者：三年了。',
                    standard_answer: '病程三年',
                    reason: '已覆盖事实点。',
                  },
                ],
              },
              latest_review: null,
              ai_evaluation: aiGenerated ? {
                id: 'ai-run-1', status: 'succeeded', provider: 'deepseek', model: 'deepseek-v4-flash',
                requested_by_id: 'teacher-1', requested_by_name: '教师甲',
                resolved_model: 'DeepSeek-V4-Flash-0731', prompt_version: 'assessment-v1',
                scoring_item_codes: ['fact:duration'], feedback_summary: '提问简洁。', latency_ms: 320,
                input_tokens: 120, output_tokens: 80, error_code: '',
                created_at: '2026-08-04T00:20:00Z', completed_at: '2026-08-04T00:20:01Z', results: [],
              } : null,
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
    expect(screen.getByText('88.89%')).toBeInTheDocument()
    expect(screen.getByText('疼痛部位')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '导出 CSV' })).toHaveAttribute('href', '/api/teacher/assignments/assignment-1/export.csv')
    fireEvent.click(screen.getByRole('button', { name: '查看答卷' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: '学生甲的答卷' })).toBeInTheDocument())
    expect(screen.getByText(/学生：疼了多久/)).toBeInTheDocument()
    expect(screen.getByText(/慢性牙周炎/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '生成 AI 辅助评价' }))
    await waitFor(() => expect(screen.getByText('评价已生成')).toBeInTheDocument())
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/session-1/ai-evaluation/'))).toBe(true)
    expect(screen.getByText(/DeepSeek-V4-Flash-0731/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('复核分数'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('改分理由（改分时必填）'), { target: { value: '追问深度不足' } })
    fireEvent.change(screen.getByLabelText('教师评语'), { target: { value: '继续加强追问' } })
    fireEvent.click(screen.getByRole('button', { name: '保存复核版本' }))

    await waitFor(() => {
      const reviewCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith('/session-1/reviews/'))
      expect(reviewCall).toBeDefined()
      expect(JSON.parse(String(reviewCall?.[1]?.body))).toEqual({
        comment: '继续加强追问',
        scores: [{ code: 'fact:duration', score: 1, reason: '追问深度不足' }],
      })
    })
  })
})
