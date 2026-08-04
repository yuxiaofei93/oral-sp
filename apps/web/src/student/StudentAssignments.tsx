import { FormEvent, useEffect, useMemo, useState } from 'react'

import {
  ApiError,
  SessionFeedback,
  SessionStage,
  SimulationSession,
  StudentAssignment,
  askPatient,
  getSessionFeedback,
  getStudentSession,
  listStudentAssignments,
  startStudentSession,
  submitSessionStage,
} from '../api/client'

const difficultyNames = { basic: '基础', intermediate: '中级', advanced: '高级' }
const attemptNames = {
  not_started: '未开始',
  active: '作答中',
  completed: '已交卷',
  expired: '已超时',
}
const stageConfig: Record<
  Exclude<SessionStage, 'interview' | 'completed'> | 'interview',
  { title: string; help: string; submissionType: string }
> = {
  interview: {
    title: '病史摘要',
    help: '确认问诊充分后提交摘要。提交后不能继续向患者提问。',
    submissionType: 'history_summary',
  },
  initial_reasoning: {
    title: '初步诊断与鉴别诊断',
    help: '写下当前判断及依据。提交后不可返回修改病史摘要。',
    submissionType: 'initial_reasoning',
  },
  test_selection: {
    title: '检查计划',
    help: '说明拟申请的检查及理由。',
    submissionType: 'test_selection',
  },
  final_reasoning: {
    title: '最终诊断与处理原则',
    help: '完成最终判断后交卷。',
    submissionType: 'final_reasoning',
  },
}

function formatTime(seconds: number) {
  const safeSeconds = Math.max(0, seconds)
  const minutes = Math.floor(safeSeconds / 60)
  const remainder = safeSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
}

function requestId() {
  return `question_${globalThis.crypto.randomUUID().replaceAll('-', '')}`
}

function Workbench({ initialSession, onExit }: { initialSession: SimulationSession; onExit: () => void }) {
  const [session, setSession] = useState(initialSession)
  const [remaining, setRemaining] = useState(initialSession.remaining_seconds)
  const [question, setQuestion] = useState('')
  const [pendingQuestion, setPendingQuestion] = useState<{ content: string; id: string } | null>(null)
  const [feedback, setFeedback] = useState<SessionFeedback | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function refreshSession() {
    const refreshed = await getStudentSession(session.id)
    setSession(refreshed)
    setRemaining(refreshed.remaining_seconds)
    return refreshed
  }

  useEffect(() => {
    if (session.status !== 'active') return
    const timer = globalThis.setInterval(() => {
      setRemaining((value) => Math.max(0, value - 1))
    }, 1000)
    return () => globalThis.clearInterval(timer)
  }, [session.status])

  useEffect(() => {
    if (remaining !== 0 || session.status !== 'active') return
    void refreshSession().catch(() => setError('无法同步交卷状态，请刷新页面。'))
  }, [remaining, session.status])

  async function handleQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const content = question.trim()
    if (!content) return
    const outgoing =
      pendingQuestion?.content === content ? pendingQuestion : { content, id: requestId() }
    setPendingQuestion(outgoing)
    setBusy(true)
    setError('')
    try {
      await askPatient(session.id, {
        content: outgoing.content,
        client_message_id: outgoing.id,
      })
      await refreshSession()
      setQuestion('')
      setPendingQuestion(null)
    } catch (requestError: unknown) {
      setError(
        requestError instanceof ApiError
          ? `${requestError.message} 再次发送会安全重试同一条问题。`
          : '患者暂时没有回答，请稍后重试。',
      )
    } finally {
      setBusy(false)
    }
  }

  async function handleStageSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (session.stage === 'completed') return
    const config = stageConfig[session.stage]
    const data = new FormData(event.currentTarget)
    setBusy(true)
    setError('')
    try {
      await submitSessionStage(session.id, {
        submission_type: config.submissionType,
        payload: { text: String(data.get('content') ?? '') },
      })
      await refreshSession()
      event.currentTarget.reset()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '阶段提交失败。')
    } finally {
      setBusy(false)
    }
  }

  async function loadFeedback() {
    setBusy(true)
    setError('')
    try {
      setFeedback(await getSessionFeedback(session.id))
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '反馈加载失败。')
    } finally {
      setBusy(false)
    }
  }

  const currentStage = session.stage === 'completed' ? null : stageConfig[session.stage]

  return (
    <section className="student-workbench" aria-labelledby="workbench-title">
      <header className="workbench-header">
        <div>
          <button className="text-button" type="button" onClick={onExit}>← 返回任务列表</button>
          <h2 id="workbench-title">{session.assignment_title}</h2>
          <p>{session.case_title} · 患者：{session.patient_name || '标准化患者'}</p>
        </div>
        <div className={`exam-timer ${remaining < 300 ? 'is-urgent' : ''}`}>
          <span>剩余时间</span>
          <strong>{formatTime(remaining)}</strong>
        </div>
      </header>

      <div className="exam-notice">整场任务限时；问题一经发出、阶段一经提交，均会留痕且不可修改或删除。</div>
      {error && <p className="form-error">{error}</p>}

      <div className="conversation" aria-label="问诊记录">
        <article className="message message--patient">
          <span>{session.patient_name || '患者'} · 开场白</span>
          <p>{session.opening_statement}</p>
        </article>
        {session.messages.map((message) => (
          <article className={`message message--${message.role}`} key={message.id}>
            <span>{message.role === 'student' ? '我' : '患者'} · #{message.sequence}</span>
            <p>{message.content}</p>
            {message.response_status === 'failed' && <small>回答生成失败，可安全重试</small>}
          </article>
        ))}
      </div>

      {session.status === 'active' && session.stage === 'interview' && (
        <form className="question-form" onSubmit={handleQuestion}>
          <label htmlFor="patient-question">向患者提问</label>
          <div>
            <input
              id="patient-question"
              value={question}
              onChange={(event) => {
                setQuestion(event.target.value)
                if (pendingQuestion?.content !== event.target.value.trim()) setPendingQuestion(null)
              }}
              maxLength={2000}
              autoComplete="off"
              required
            />
            <button className="button" type="submit" disabled={busy}>发送问题</button>
          </div>
        </form>
      )}

      {session.status === 'active' && currentStage && (
        <form className="stage-form" onSubmit={handleStageSubmit}>
          <h3>{currentStage.title}</h3>
          <p>{currentStage.help}</p>
          <textarea name="content" rows={5} required />
          <button className="button" type="submit" disabled={busy}>
            {session.stage === 'final_reasoning' ? '提交并交卷' : '提交并进入下一阶段'}
          </button>
        </form>
      )}

      {session.status !== 'active' && (
        <section className="feedback-card">
          <h3>{session.status === 'completed' ? '已完成交卷' : '本次作答已超时'}</h3>
          {!feedback ? (
            <button className="button button--secondary" type="button" onClick={loadFeedback} disabled={busy}>
              查看教师已发布反馈
            </button>
          ) : (
            <div className="feedback-content">
              <div className="feedback-score">
                <strong>{feedback.score.final_score}</strong>
                <span>/ {feedback.score.scored_maximum} 当前得分</span>
                {feedback.score.final_score !== feedback.score.automatic_score && <small>规则得分 {feedback.score.automatic_score}，当前得分还包含 AI 辅助评价或教师复核</small>}
                {feedback.score.provisional && <small>总分 {feedback.score.maximum_score}，仍有待评价项</small>}
              </div>
              <p>{feedback.feedback_summary}</p>
              <h4>分项得分</h4>
              <div className="feedback-items">
                {feedback.scoring_items.map((item) => (
                  <article key={item.code}>
                    <div><strong>{item.label}</strong><span>{item.effective_score === null ? '待评价' : `${item.effective_score} / ${item.max_score}`}</span></div>
                    {item.adjustment_reason && <small>教师复核：{item.adjustment_reason}</small>}
                    <p>{item.reason}</p>
                    {item.evidence_excerpt && <small>证据：{item.evidence_excerpt}</small>}
                    {item.ai_score !== null && <small>AI 辅助评分：{item.ai_score} / {item.max_score}（置信度 {Math.round((item.ai_confidence ?? 0) * 100)}%）</small>}
                    {item.ai_reason && <p>AI 评分理由：{item.ai_reason}</p>}
                    {item.ai_evidence_excerpt && <small>AI 引用证据：{item.ai_evidence_excerpt}</small>}
                    {item.ai_feedback && <small>AI 改进建议：{item.ai_feedback}</small>}
                    {item.standard_answer && <small>标准答案：{item.standard_answer}</small>}
                  </article>
                ))}
              </div>
              {feedback.omissions.length > 0 && <><h4>遗漏项</h4>{feedback.omissions.map((item) => <p key={item.code}>{item.label}：{item.reason}</p>)}</>}
              {feedback.errors.length > 0 && <><h4>需关注的错误项</h4>{feedback.errors.map((item) => <p key={item.code}>{item.label}：{item.reason}</p>)}</>}
              <h4>标准诊断</h4>
              {feedback.standard_diagnoses.map((diagnosis) => <p key={`${diagnosis.type}-${diagnosis.name}`}>{diagnosis.name}</p>)}
              <h4>标准检查</h4>
              {feedback.standard_tests.map((test) => <p key={test.code}>{test.name}：{test.result}</p>)}
              {feedback.ai_feedback && <><h4>AI 辅助评语</h4><p>{feedback.ai_feedback}</p></>}
              {feedback.teacher_comment && <><h4>教师评语</h4><p>{feedback.teacher_comment}</p></>}
            </div>
          )}
        </section>
      )}
    </section>
  )
}

export function StudentAssignments() {
  const [assignments, setAssignments] = useState<StudentAssignment[]>([])
  const [session, setSession] = useState<SimulationSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function loadAssignments() {
    setLoading(true)
    setError('')
    try {
      setAssignments(await listStudentAssignments())
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '任务列表加载失败。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadAssignments()
  }, [])

  const now = useMemo(() => Date.now(), [assignments])

  async function openAssignment(assignment: StudentAssignment) {
    setLoading(true)
    setError('')
    try {
      if (assignment.attempt_status === 'not_started' || assignment.attempt_status === 'active') {
        const result = await startStudentSession(assignment.id)
        setSession(result.session)
      } else if (assignment.session_id) {
        setSession(await getStudentSession(assignment.session_id))
      }
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '无法进入任务。')
    } finally {
      setLoading(false)
    }
  }

  if (session) {
    return <Workbench initialSession={session} onExit={() => { setSession(null); void loadAssignments() }} />
  }

  return (
    <section className="student-workspace" aria-labelledby="student-tasks-title">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">STUDENT EXAMS</p>
          <h2 id="student-tasks-title">我的问诊任务</h2>
          <p>每个任务仅有一次作答机会。开始后由服务端记录倒计时。</p>
        </div>
      </header>
      {error && <p className="form-error">{error}</p>}
      {loading && <p className="empty-state">正在加载任务…</p>}
      {!loading && assignments.length === 0 && <p className="empty-state">目前没有分配给你的任务。</p>}
      <div className="assignment-list">
        {assignments.map((assignment) => {
          const notOpen = Date.parse(assignment.opens_at) > now
          const unavailable = assignment.status === 'closed' || Date.parse(assignment.deadline_at) <= now
          return (
            <article key={assignment.id}>
              <div>
                <span>{difficultyNames[assignment.difficulty]} · {assignment.duration_minutes} 分钟</span>
                <h3>{assignment.title}</h3>
                <p>{assignment.case_title}</p>
              </div>
              <div className="assignment-list__action">
                <span>{attemptNames[assignment.attempt_status]}</span>
                <button
                  className="button button--secondary"
                  type="button"
                  disabled={loading || (assignment.attempt_status === 'not_started' && (notOpen || unavailable))}
                  onClick={() => openAssignment(assignment)}
                >
                  {assignment.attempt_status === 'not_started' ? '开始作答' : assignment.attempt_status === 'active' ? '继续作答' : '查看记录'}
                </button>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
