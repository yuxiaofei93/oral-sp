import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { StudentAssignments } from './StudentAssignments'

const session = {
  id: 'session-1',
  assignment_id: 'assignment-1',
  assignment_title: '牙周问诊练习',
  patient_name: '陈女士',
  opening_statement: '医生您好，我的牙龈总是疼。',
  status: 'active',
  stage: 'interview',
  started_at: '2026-08-04T01:00:00Z',
  deadline_at: '2099-08-04T01:20:00Z',
  completed_at: null,
  remaining_seconds: 1200,
  messages: [],
  submissions: [],
}

describe('StudentAssignments', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('starts an assigned exam and records an idempotent patient question', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/student/assignments/')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                id: 'assignment-1',
                title: '牙周问诊练习',
                difficulty: 'intermediate',
                duration_minutes: 20,
                opens_at: '2026-08-04T00:00:00Z',
                deadline_at: '2099-08-04T02:00:00Z',
                status: 'open',
                feedback_released_at: null,
                attempt_status: 'not_started',
                session_id: null,
              },
            ]),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"student-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/assignment-1/session/')) {
        return Promise.resolve(new Response(JSON.stringify({ created: true, session }), { status: 201 }))
      }
      if (url.endsWith('/session-1/messages/')) {
        const body = JSON.parse(String(init?.body))
        expect(body.client_message_id).toMatch(/^question_[a-f0-9]+$/)
        return Promise.resolve(
          new Response(
            JSON.stringify({
              reused: false,
              student_message: { id: 'm1' },
              patient_message: { id: 'm2' },
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/student/sessions/session-1/')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...session,
              messages: [
                { id: 'm1', sequence: 1, role: 'student', content: '有多久了？', response_status: 'completed' },
                { id: 'm2', sequence: 2, role: 'patient', content: '差不多三年。', response_status: 'not_applicable' },
              ],
            }),
            { status: 200 },
          ),
        )
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<StudentAssignments />)
    await waitFor(() => screen.getByRole('button', { name: '开始作答' }))
    fireEvent.click(screen.getByRole('button', { name: '开始作答' }))
    await waitFor(() => screen.getByRole('heading', { name: '牙周问诊练习' }))

    fireEvent.change(screen.getByLabelText('向患者提问'), { target: { value: '有多久了？' } })
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }))

    await waitFor(() => expect(screen.getByText('差不多三年。')).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalled()
  })

  it('advances to the next stage without reporting a false submission failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/student/assignments/')) {
        return Promise.resolve(new Response(JSON.stringify([{
          id: 'assignment-1',
          title: '牙周问诊练习',
          difficulty: 'intermediate',
          duration_minutes: 20,
          opens_at: '2026-08-04T00:00:00Z',
          deadline_at: '2099-08-04T02:00:00Z',
          status: 'open',
          feedback_released_at: null,
          attempt_status: 'active',
          session_id: 'session-1',
        }]), { status: 200 }))
      }
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"student-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/assignment-1/session/')) {
        return Promise.resolve(new Response(JSON.stringify({ created: false, session }), { status: 200 }))
      }
      if (url.endsWith('/session-1/submissions/')) {
        expect(JSON.parse(String(init?.body))).toEqual({
          submission_type: 'history_summary',
          payload: { text: '牙龈疼痛约三年。' },
        })
        return Promise.resolve(new Response(JSON.stringify({
          id: 'submission-1',
          submission_type: 'history_summary',
          payload: { text: '牙龈疼痛约三年。' },
          submitted_at: '2026-08-06T01:00:00Z',
        }), { status: 201 }))
      }
      if (url.endsWith('/student/sessions/session-1/')) {
        return Promise.resolve(new Response(JSON.stringify({
          ...session,
          stage: 'initial_reasoning',
          submissions: [{
            id: 'submission-1',
            submission_type: 'history_summary',
            payload: { text: '牙龈疼痛约三年。' },
            submitted_at: '2026-08-06T01:00:00Z',
          }],
        }), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<StudentAssignments />)
    await waitFor(() => screen.getByRole('button', { name: '继续作答' }))
    fireEvent.click(screen.getByRole('button', { name: '继续作答' }))
    await waitFor(() => screen.getByRole('heading', { name: '病史摘要' }))

    const stageAnswer = screen.getByRole('textbox', { name: '病史摘要' })
    fireEvent.change(stageAnswer, { target: { value: '牙龈疼痛约三年。' } })
    fireEvent.click(screen.getByRole('button', { name: '提交并进入下一阶段' }))

    await waitFor(() => expect(screen.getByRole('heading', {
      name: '初步诊断与鉴别诊断',
    })).toBeInTheDocument())
    expect(screen.queryByText('阶段提交失败。')).not.toBeInTheDocument()
  })

  it('shows released score, omissions and standard answers only from feedback API', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/student/assignments/')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                id: 'assignment-1',
                title: '牙周问诊练习',
                difficulty: 'intermediate',
                duration_minutes: 20,
                opens_at: '2026-08-04T00:00:00Z',
                deadline_at: '2026-08-04T02:00:00Z',
                status: 'closed',
                feedback_released_at: '2026-08-04T03:00:00Z',
                attempt_status: 'completed',
                session_id: 'session-1',
              },
            ]),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/student/sessions/session-1/feedback/')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              session_id: 'session-1',
              score: { automatic_score: 6, final_score: 7, scored_maximum: 8, maximum_score: 9, provisional: true },
              scoring_items: [
                { code: 'score.final', label: '最终诊断', automatic_score: 0, teacher_score: 1, effective_score: 1, adjustment_reason: '诊断方向基本正确。', max_score: 3, decision: 'missed', effective_decision: 'partial', reason: '未命中标准诊断。', evidence_excerpt: '未明确', standard_answer: '慢性牙周炎' },
              ],
              omissions: [{ code: 'score.final', label: '最终诊断', reason: '未命中标准诊断。', standard_answer: '慢性牙周炎' }],
              errors: [],
              feedback_summary: '发现 1 个遗漏项。',
              ai_feedback: null,
              teacher_comment: '建议补充诊断依据。',
              standard_diagnoses: [{ type: 'final', name: '慢性牙周炎', supporting_evidence: [] }],
              standard_tests: [{ code: 'probe', name: '牙周探诊', result: '探诊深度增加', interpretation: '支持诊断' }],
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/student/sessions/session-1/')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...session,
              status: 'completed',
              stage: 'completed',
              remaining_seconds: 0,
            }),
            { status: 200 },
          ),
        )
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<StudentAssignments />)
    await waitFor(() => screen.getByRole('button', { name: '查看记录' }))
    fireEvent.click(screen.getByRole('button', { name: '查看记录' }))
    await waitFor(() => screen.getByRole('button', { name: '查看教师已发布反馈' }))
    fireEvent.click(screen.getByRole('button', { name: '查看教师已发布反馈' }))

    await waitFor(() => expect(screen.getByText('7')).toBeInTheDocument())
    expect(screen.getAllByText(/慢性牙周炎/).length).toBeGreaterThan(0)
    expect(screen.getByText(/发现 1 个遗漏项/)).toBeInTheDocument()
    expect(screen.getByText('建议补充诊断依据。')).toBeInTheDocument()
  })
})
