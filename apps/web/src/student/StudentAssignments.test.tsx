import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
  physical_exam_result: null,
}

describe('StudentAssignments', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('starts an assigned exam and records an idempotent patient question', async () => {
    let resolvePatientQuestion: ((response: Response) => void) | undefined
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
        return new Promise<Response>((resolve) => {
          resolvePatientQuestion = resolve
        })
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
    expect(await screen.findByRole('heading', { name: '问诊任务' })).toBeInTheDocument()
    expect(screen.queryByText('STUDENT EXAMS')).not.toBeInTheDocument()
    expect(screen.queryByText('每个任务仅有一次作答机会。开始后由服务端记录倒计时。')).not.toBeInTheDocument()
    await waitFor(() => screen.getByRole('button', { name: '开始作答' }))
    fireEvent.click(screen.getByRole('button', { name: '开始作答' }))
    await waitFor(() => screen.getByRole('heading', { name: '牙周问诊练习' }))
    expect(screen.getByRole('navigation', { name: '问诊阶段' })).toBeInTheDocument()
    expect(screen.getByText('问诊采集').closest('li')).toHaveAttribute('aria-current', 'step')
    expect(screen.queryByText('标准化患者在线')).not.toBeInTheDocument()
    expect(screen.queryByText(/条记录/)).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText('输入你想向患者了解的问题…')).toBeInTheDocument()
    expect(screen.getByText('病例编辑')).toBeInTheDocument()
    const basicInformation = screen.getByRole('region', { name: '基本信息' })
    expect(basicInformation).toHaveTextContent('患者化名陈女士')
    expect(basicInformation).toHaveTextContent('科室口腔粘膜科')
    expect(basicInformation).toHaveTextContent('就诊日期2026-08-04')
    expect(within(basicInformation).getByText(/^\d{8}$/)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '诊断' })).toHaveAttribute('readonly')

    const conversation = screen.getByLabelText('问诊记录')
    Object.defineProperty(conversation, 'scrollHeight', { configurable: true, value: 500 })
    fireEvent.change(screen.getByLabelText('向患者提问'), { target: { value: '有多久了？' } })
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }))

    const outgoingMessage = await screen.findByText('有多久了？')
    const thinking = screen.getByRole('status')
    expect(thinking).toHaveTextContent('患者正在思考')
    expect(outgoingMessage.compareDocumentPosition(thinking) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByRole('button', { name: '提交并进入下一阶段' })).toBeEnabled()
    expect(conversation.scrollTop).toBe(500)

    act(() => {
      resolvePatientQuestion?.(
        new Response(
          JSON.stringify({
            reused: false,
            interaction_type: 'patient_answer',
            student_message: { id: 'm1' },
            patient_message: { id: 'm2' },
          }),
          { status: 200 },
        ),
      )
    })
    await waitFor(() => expect(screen.getByText('差不多三年。')).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalled()
  })

  it('advances to the next stage without reporting a false submission failure', async () => {
    const historyPayload = {
      text: '主诉：牙龈疼痛约三年。\n现病史：三年前开始反复牙龈疼痛。\n既往史：否认重大疾病史。\n家族史：无相关家族史。',
      chief_complaint: '牙龈疼痛约三年。',
      present_illness: '三年前开始反复牙龈疼痛。',
      past_history: '否认重大疾病史。',
      family_history: '无相关家族史。',
      specialty_exam: '',
    }
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
          payload: historyPayload,
        })
        return Promise.resolve(new Response(JSON.stringify({
          id: 'submission-1',
          submission_type: 'history_summary',
          payload: historyPayload,
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
            payload: historyPayload,
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

    fireEvent.change(screen.getByRole('textbox', { name: '主诉' }), {
      target: { value: historyPayload.chief_complaint },
    })
    fireEvent.change(screen.getByRole('textbox', { name: '现病史' }), {
      target: { value: historyPayload.present_illness },
    })
    fireEvent.change(screen.getByRole('textbox', { name: '既往史' }), {
      target: { value: historyPayload.past_history },
    })
    fireEvent.change(screen.getByRole('textbox', { name: '家族史' }), {
      target: { value: historyPayload.family_history },
    })
    fireEvent.click(screen.getByRole('button', { name: '提交并进入下一阶段' }))

    await waitFor(() => expect(screen.getByRole('heading', {
      name: '初步诊断与鉴别诊断',
    })).toBeInTheDocument())
    expect(screen.getByRole('textbox', { name: '主诉' })).toHaveAttribute('readonly')
    expect(screen.getByRole('textbox', { name: '诊断' })).not.toHaveAttribute('readonly')
    expect(screen.queryByText('阶段提交失败。')).not.toBeInTheDocument()
  })

  it('opens released physical exam results and keeps a reusable transcript link', async () => {
    const physicalExamResult = {
      release_id: 'release-1',
      released_at: '2026-08-04T01:03:00Z',
      access_reason: 'triggered',
      findings_text: '右下后牙区牙龈红肿，局部可见瘘管。',
      images: [{
        id: 1,
        kind: 'image',
        display_order: 0,
        filename: '口内照.jpg',
        content_type: 'image/jpeg',
        size_bytes: 2048,
        deidentified_confirmed: true,
        content_url: '/api/student/sessions/session-1/physical-exam/assets/1/content/',
      }],
      attachments: [{
        id: 2,
        kind: 'attachment',
        display_order: 0,
        filename: '检查记录.custom',
        content_type: 'application/x-custom',
        size_bytes: 1024,
        deidentified_confirmed: true,
        content_url: '/api/student/sessions/session-1/physical-exam/assets/2/content/',
      }],
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
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
          attempt_status: 'not_started',
          session_id: null,
        }]), { status: 200 }))
      }
      if (url.endsWith('/csrf/')) {
        return Promise.resolve(new Response('{"csrf_token":"student-csrf"}', { status: 200 }))
      }
      if (url.endsWith('/assignment-1/session/')) {
        return Promise.resolve(new Response(JSON.stringify({ created: true, session }), { status: 201 }))
      }
      if (url.endsWith('/session-1/messages/')) {
        return Promise.resolve(new Response(JSON.stringify({
          reused: false,
          interaction_type: 'physical_exam_released',
          student_message: { id: 'm1' },
          patient_message: { id: 'm2' },
        }), { status: 200 }))
      }
      if (url.endsWith('/student/sessions/session-1/')) {
        return Promise.resolve(new Response(JSON.stringify({
          ...session,
          physical_exam_result: physicalExamResult,
          messages: [
            { id: 'm1', sequence: 1, role: 'student', kind: 'chat', content: '可以检查一下您的口腔吗？', response_status: 'completed' },
            { id: 'm2', sequence: 2, role: 'patient', kind: 'physical_exam_consent', content: '可以，麻烦您检查吧。', response_status: 'not_applicable' },
            { id: 'm3', sequence: 3, role: 'system', kind: 'physical_exam_result', content: physicalExamResult.findings_text, response_status: 'not_applicable' },
          ],
        }), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected request: ${url}`))
    })

    render(<StudentAssignments />)
    fireEvent.click(await screen.findByRole('button', { name: '开始作答' }))
    await waitFor(() => screen.getByLabelText('向患者提问'))
    fireEvent.change(screen.getByLabelText('向患者提问'), {
      target: { value: '可以检查一下您的口腔吗？' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }))

    const dialog = await screen.findByRole('dialog', { name: '口腔体格检查所见' })
    expect(dialog).toHaveTextContent('右下后牙区牙龈红肿，局部可见瘘管。')
    expect(within(screen.getByRole('region', { name: /专科检查/ })).getByText(
      '右下后牙区牙龈红肿，局部可见瘘管。',
    )).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /检查记录.custom/ })).toHaveAttribute(
      'href',
      physicalExamResult.attachments[0].content_url,
    )
    fireEvent.click(screen.getByRole('button', { name: '关闭体格检查结果' }))
    expect(screen.queryByRole('dialog', { name: '口腔体格检查所见' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '查看完整体格检查资料' }))
    expect(screen.getByRole('dialog', { name: '口腔体格检查所见' })).toBeInTheDocument()
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
