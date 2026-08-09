import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'

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
import { PhysicalExamDialog } from '../PhysicalExamDialog'

const difficultyNames = { basic: '基础', intermediate: '中级', advanced: '高级' }
const attemptNames = {
  not_started: '未开始',
  active: '作答中',
  completed: '已交卷',
  expired: '已超时',
}
const stageConfig: Record<
  Exclude<SessionStage, 'interview' | 'completed'> | 'interview',
  { title: string; shortTitle: string; help: string; submissionType: string }
> = {
  interview: {
    title: '病史摘要',
    shortTitle: '问诊采集',
    help: '确认问诊充分后提交摘要。提交后不能继续向患者提问。',
    submissionType: 'history_summary',
  },
  initial_reasoning: {
    title: '初步诊断与鉴别诊断',
    shortTitle: '初步判断',
    help: '写下当前判断及依据。提交后不可返回修改病史摘要。',
    submissionType: 'initial_reasoning',
  },
  test_selection: {
    title: '检查计划',
    shortTitle: '检查计划',
    help: '说明拟申请的检查及理由。',
    submissionType: 'test_selection',
  },
  final_reasoning: {
    title: '最终诊断与处理原则',
    shortTitle: '最终诊断',
    help: '完成最终判断后交卷。',
    submissionType: 'final_reasoning',
  },
}

type CaseDraft = {
  chiefComplaint: string
  presentIllness: string
  pastHistory: string
  familyHistory: string
  diagnosis: string
  treatment: string
  medicalAdvice: string
}

const emptyCaseDraft: CaseDraft = {
  chiefComplaint: '',
  presentIllness: '',
  pastHistory: '',
  familyHistory: '',
  diagnosis: '',
  treatment: '',
  medicalAdvice: '',
}

const stageOrder: Array<Exclude<SessionStage, 'completed'>> = [
  'interview',
  'initial_reasoning',
  'test_selection',
  'final_reasoning',
]

function formatTime(seconds: number) {
  const safeSeconds = Math.max(0, seconds)
  const minutes = Math.floor(safeSeconds / 60)
  const remainder = safeSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
}

function requestId() {
  return `question_${globalThis.crypto.randomUUID().replaceAll('-', '')}`
}

function payloadText(payload: Record<string, unknown>, key: string) {
  const value = payload[key]
  return typeof value === 'string' ? value : ''
}

function initialCaseDraft(submissions: SimulationSession['submissions']): CaseDraft {
  return submissions.reduce<CaseDraft>((draft, submission) => {
    const { payload } = submission
    if (submission.submission_type === 'history_summary') {
      return {
        ...draft,
        chiefComplaint: payloadText(payload, 'chief_complaint'),
        presentIllness: payloadText(payload, 'present_illness') || payloadText(payload, 'text'),
        pastHistory: payloadText(payload, 'past_history'),
        familyHistory: payloadText(payload, 'family_history'),
      }
    }
    if (submission.submission_type === 'initial_reasoning') {
      return { ...draft, diagnosis: payloadText(payload, 'diagnosis') || payloadText(payload, 'text') }
    }
    if (submission.submission_type === 'test_selection') {
      return { ...draft, treatment: payloadText(payload, 'treatment') || payloadText(payload, 'text') }
    }
    if (submission.submission_type === 'final_reasoning') {
      return {
        ...draft,
        diagnosis: payloadText(payload, 'diagnosis') || draft.diagnosis,
        treatment: payloadText(payload, 'treatment') || draft.treatment,
        medicalAdvice: payloadText(payload, 'medical_advice'),
      }
    }
    return draft
  }, emptyCaseDraft)
}

function visitDate(startedAt: string) {
  const date = new Date(startedAt)
  if (Number.isNaN(date.getTime())) return startedAt.slice(0, 10)
  const parts = new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date)
  const value = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value ?? ''
  return `${value('year')}-${value('month')}-${value('day')}`
}

function recordNumber(sessionId: string) {
  let hash = 0
  for (const character of sessionId) hash = (hash * 31 + character.charCodeAt(0)) >>> 0
  return String(10_000_000 + (hash % 90_000_000))
}

function stagePayload(stage: Exclude<SessionStage, 'completed'>, draft: CaseDraft, examText: string) {
  if (stage === 'interview') {
    const text = [
      `主诉：${draft.chiefComplaint}`,
      `现病史：${draft.presentIllness}`,
      `既往史：${draft.pastHistory}`,
      `家族史：${draft.familyHistory}`,
      examText ? `专科检查：${examText}` : '',
    ].filter(Boolean).join('\n')
    return {
      text,
      chief_complaint: draft.chiefComplaint,
      present_illness: draft.presentIllness,
      past_history: draft.pastHistory,
      family_history: draft.familyHistory,
      specialty_exam: examText,
    }
  }
  if (stage === 'initial_reasoning') {
    return { text: draft.diagnosis, diagnosis: draft.diagnosis }
  }
  if (stage === 'test_selection') {
    return { text: draft.treatment, treatment: draft.treatment }
  }
  const text = [
    `诊断：${draft.diagnosis}`,
    `处理：${draft.treatment}`,
    `医嘱：${draft.medicalAdvice}`,
  ].join('\n')
  return {
    text,
    diagnosis: draft.diagnosis,
    treatment: draft.treatment,
    medical_advice: draft.medicalAdvice,
  }
}

function Workbench({ initialSession, onExit }: { initialSession: SimulationSession; onExit: () => void }) {
  const [session, setSession] = useState(initialSession)
  const [remaining, setRemaining] = useState(initialSession.remaining_seconds)
  const [question, setQuestion] = useState('')
  const [pendingQuestion, setPendingQuestion] = useState<{ content: string; id: string } | null>(null)
  const [caseDraft, setCaseDraft] = useState<CaseDraft>(() => initialCaseDraft(initialSession.submissions))
  const [feedback, setFeedback] = useState<SessionFeedback | null>(null)
  const [physicalExamOpen, setPhysicalExamOpen] = useState(false)
  const [questionBusy, setQuestionBusy] = useState(false)
  const [stageBusy, setStageBusy] = useState(false)
  const [feedbackBusy, setFeedbackBusy] = useState(false)
  const [error, setError] = useState('')
  const conversationRef = useRef<HTMLDivElement>(null)

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

  useEffect(() => {
    const conversation = conversationRef.current
    if (!conversation) return
    conversation.scrollTop = conversation.scrollHeight
  }, [session.messages.length, pendingQuestion])

  async function handleQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const content = question.trim()
    if (!content) return
    const outgoing =
      pendingQuestion?.content === content ? pendingQuestion : { content, id: requestId() }
    setPendingQuestion(outgoing)
    setQuestionBusy(true)
    setError('')
    try {
      const exchange = await askPatient(session.id, {
        content: outgoing.content,
        client_message_id: outgoing.id,
      })
      await refreshSession()
      if (exchange.interaction_type !== 'patient_answer') setPhysicalExamOpen(true)
      setQuestion('')
      setPendingQuestion(null)
    } catch (requestError: unknown) {
      setError(
        requestError instanceof ApiError
          ? `${requestError.message} 再次发送会安全重试同一条问题。`
          : '患者暂时没有回答，请稍后重试。',
      )
    } finally {
      setQuestionBusy(false)
    }
  }

  async function handleStageSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (session.stage === 'completed') return
    const config = stageConfig[session.stage]
    setStageBusy(true)
    setError('')
    try {
      await submitSessionStage(session.id, {
        submission_type: config.submissionType,
        payload: stagePayload(session.stage, caseDraft, session.physical_exam_result?.findings_text ?? ''),
      })
      try {
        await refreshSession()
      } catch {
        setError('本阶段已提交成功，但页面状态同步失败，请刷新页面继续。')
      }
    } catch (requestError: unknown) {
      try {
        const refreshed = await refreshSession()
        const submissionExists = refreshed.submissions.some(
          (submission) => submission.submission_type === config.submissionType,
        )
        if (submissionExists) {
          return
        }
      } catch {
        // Keep the original submission error when server state cannot be reconciled.
      }
      setError(requestError instanceof ApiError ? requestError.message : '阶段提交失败。')
    } finally {
      setStageBusy(false)
    }
  }

  async function loadFeedback() {
    setFeedbackBusy(true)
    setError('')
    try {
      setFeedback(await getSessionFeedback(session.id))
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '反馈加载失败。')
    } finally {
      setFeedbackBusy(false)
    }
  }

  const currentStage = session.stage === 'completed' ? null : stageConfig[session.stage]
  const currentStageIndex = session.stage === 'completed' ? stageOrder.length : stageOrder.indexOf(session.stage)
  const patientName = session.patient_name || '标准化患者'
  const availablePhysicalExam = session.physical_exam_result ?? feedback?.physical_exam_result ?? null
  const isHistoryEditable = session.stage === 'interview'
  const isDiagnosisEditable = session.stage === 'initial_reasoning' || session.stage === 'final_reasoning'
  const isTreatmentEditable = session.stage === 'test_selection' || session.stage === 'final_reasoning'
  const isAdviceEditable = session.stage === 'final_reasoning'

  function updateCaseDraft(field: keyof CaseDraft, value: string) {
    setCaseDraft((current) => ({ ...current, [field]: value }))
  }

  return (
    <section className="student-workbench" aria-labelledby="workbench-title">
      <header className="workbench-header">
        <div className="workbench-header__identity">
          <button className="workbench-back" type="button" onClick={onExit} aria-label="返回任务列表">
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="m15 18-6-6 6-6" />
            </svg>
          </button>
          <div>
            <div className="workbench-kicker">
              <span>{session.status === 'active' ? '进行中的问诊' : '问诊记录'}</span>
              <i aria-hidden="true" />
              <span>患者 {patientName}</span>
            </div>
            <h2 id="workbench-title">{session.assignment_title}</h2>
          </div>
        </div>
        <div className={`exam-timer ${session.status === 'active' && remaining < 300 ? 'is-urgent' : ''}`}>
          <span className="exam-timer__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="8.5" />
              <path d="M12 7.5V12l3 2" />
            </svg>
          </span>
          <span>
            <small>{session.status === 'active' ? '剩余时间' : '作答已结束'}</small>
            <strong>{formatTime(remaining)}</strong>
          </span>
        </div>
      </header>

      <nav className="stage-progress" aria-label="问诊阶段">
        <ol>
          {stageOrder.map((stage, index) => {
            const state = index < currentStageIndex ? 'complete' : index === currentStageIndex ? 'current' : 'upcoming'
            return (
              <li className={`stage-progress__item is-${state}`} key={stage} aria-current={state === 'current' ? 'step' : undefined}>
                <span className="stage-progress__marker" aria-hidden="true">
                  {state === 'complete' ? (
                    <svg viewBox="0 0 24 24"><path d="m7 12.5 3.2 3.2L17.5 8.5" /></svg>
                  ) : index + 1}
                </span>
                <span>
                  <small>阶段 {index + 1}</small>
                  <strong>{stageConfig[stage].shortTitle}</strong>
                </span>
              </li>
            )
          })}
        </ol>
      </nav>

      <div className="exam-notice">
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path d="M12 8v4.5M12 16h.01" />
          <circle cx="12" cy="12" r="9" />
        </svg>
        <span>整场任务限时，问题发送和阶段提交后将自动留痕，无法修改或删除。</span>
      </div>
      {error && <p className="form-error workbench-error" role="alert">{error}</p>}

      <div className={`workbench-layout ${session.status !== 'active' ? 'is-review' : ''}`}>
        <section className="consultation-panel" aria-labelledby="consultation-title">
          <header className="consultation-panel__header">
            <span className="patient-avatar" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <circle cx="12" cy="8" r="3.25" />
                <path d="M5.5 19c.7-3.6 2.8-5.4 6.5-5.4s5.8 1.8 6.5 5.4" />
              </svg>
            </span>
            <div>
              <h3 id="consultation-title">与{patientName}问诊</h3>
            </div>
          </header>

          <div className="conversation" aria-label="问诊记录" ref={conversationRef}>
            <article className="message message--patient">
              <span>{patientName} · 开场白</span>
              <p>{session.opening_statement}</p>
            </article>
            {session.messages.map((message) => (
              <article className={`message message--${message.role}`} key={message.id}>
                <span>{message.role === 'student' ? '我' : message.role === 'system' ? '系统 · 体格检查' : patientName} · #{message.sequence}</span>
                <p>{message.content}</p>
                {message.kind === 'physical_exam_result' && availablePhysicalExam && (
                  <button className="physical-exam-message-link" type="button" onClick={() => setPhysicalExamOpen(true)}>
                    查看完整体格检查资料
                  </button>
                )}
                {message.response_status === 'failed' && <small>回答生成失败，可安全重试</small>}
              </article>
            ))}
            {pendingQuestion && (
              <>
                <article className="message message--student message--pending">
                  <span>我 · 发送中</span>
                  <p>{pendingQuestion.content}</p>
                </article>
                {questionBusy && (
                  <div className="patient-thinking" role="status">
                    <span /><span /><span />
                    <small>患者正在思考</small>
                  </div>
                )}
              </>
            )}
          </div>

          {session.status === 'active' && session.stage === 'interview' ? (
            <form className="question-form" onSubmit={handleQuestion}>
              <label className="visually-hidden" htmlFor="patient-question">向患者提问</label>
              <div>
                <input
                  id="patient-question"
                  value={question}
                  disabled={questionBusy}
                  onChange={(event) => {
                    setQuestion(event.target.value)
                    if (pendingQuestion?.content !== event.target.value.trim()) setPendingQuestion(null)
                  }}
                  placeholder="输入你想向患者了解的问题…"
                  maxLength={2000}
                  autoComplete="off"
                  required
                />
                <button className="button question-form__submit" type="submit" disabled={questionBusy} aria-label="发送问题">
                  <span>{questionBusy ? '发送中' : '发送'}</span>
                  <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m5 12 14-7-4.5 14-3-5.5L5 12Z" /><path d="m11.5 13.5 3-3" /></svg>
                </button>
              </div>
              <small>请一次询问一个清晰的问题，患者会根据病例信息作答。</small>
            </form>
          ) : session.status === 'active' ? (
            <div className="conversation-locked">
              <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="6" y="10" width="12" height="9" rx="2" /><path d="M8.5 10V7.5a3.5 3.5 0 0 1 7 0V10" /></svg>
              问诊阶段已结束，对话记录仅供回顾
            </div>
          ) : null}
        </section>

        {session.status === 'active' && currentStage && (
          <aside className="clinical-panel" aria-labelledby="stage-title">
            <div className="clinical-panel__heading">
              <span>病例编辑</span>
              <b>{Math.min(currentStageIndex + 1, stageOrder.length)} / {stageOrder.length}</b>
            </div>
            <form className="case-record-form" onSubmit={handleStageSubmit}>
              <div className="case-record-form__stage">
                <span>当前阶段</span>
                <h3 id="stage-title">{currentStage.title}</h3>
                <p>{currentStage.help}</p>
              </div>

              <section className="case-record-section case-record-section--identity" aria-labelledby="case-section-identity">
                <h3 id="case-section-identity"><span aria-hidden="true">1</span>基本信息</h3>
                <dl>
                  <div><dt>患者化名</dt><dd>{patientName}</dd></div>
                  <div><dt>科室</dt><dd>口腔粘膜科</dd></div>
                  <div><dt>就诊日期</dt><dd>{visitDate(session.started_at)}</dd></div>
                  <div><dt>流水号</dt><dd>{recordNumber(session.id)}</dd></div>
                </dl>
              </section>

              <section className="case-record-section" aria-labelledby="case-section-chief-complaint">
                <label htmlFor="case-chief-complaint">
                  <h3 id="case-section-chief-complaint"><span aria-hidden="true">2</span>主诉</h3>
                </label>
                <textarea
                  id="case-chief-complaint"
                  value={caseDraft.chiefComplaint}
                  onChange={(event) => updateCaseDraft('chiefComplaint', event.target.value)}
                  placeholder={isHistoryEditable ? '请用一段文字记录患者此次就诊的主要症状及持续时间…' : '本阶段已提交'}
                  rows={3}
                  readOnly={!isHistoryEditable}
                  required={isHistoryEditable}
                />
              </section>

              <section className="case-record-section" aria-labelledby="case-section-present-illness">
                <label htmlFor="case-present-illness">
                  <h3 id="case-section-present-illness"><span aria-hidden="true">3</span>现病史</h3>
                </label>
                <textarea
                  id="case-present-illness"
                  value={caseDraft.presentIllness}
                  onChange={(event) => updateCaseDraft('presentIllness', event.target.value)}
                  placeholder={isHistoryEditable ? '请记录本次疾病的发生、发展及诊疗经过…' : '本阶段已提交'}
                  rows={3}
                  readOnly={!isHistoryEditable}
                  required={isHistoryEditable}
                />
              </section>

              <section className="case-record-section" aria-labelledby="case-section-past-history">
                <label htmlFor="case-past-history">
                  <h3 id="case-section-past-history"><span aria-hidden="true">4</span>既往史</h3>
                </label>
                <textarea
                  id="case-past-history"
                  value={caseDraft.pastHistory}
                  onChange={(event) => updateCaseDraft('pastHistory', event.target.value)}
                  placeholder={isHistoryEditable ? '请记录既往疾病、手术、过敏及用药等情况…' : '本阶段已提交'}
                  rows={3}
                  readOnly={!isHistoryEditable}
                  required={isHistoryEditable}
                />
              </section>

              <section className="case-record-section" aria-labelledby="case-section-family-history">
                <label htmlFor="case-family-history">
                  <h3 id="case-section-family-history"><span aria-hidden="true">5</span>家族史</h3>
                </label>
                <textarea
                  id="case-family-history"
                  value={caseDraft.familyHistory}
                  onChange={(event) => updateCaseDraft('familyHistory', event.target.value)}
                  placeholder={isHistoryEditable ? '请记录家族中相关疾病及遗传病史…' : '本阶段已提交'}
                  rows={3}
                  readOnly={!isHistoryEditable}
                  required={isHistoryEditable}
                />
              </section>

              <section className="case-record-section" aria-labelledby="case-section-exam">
                <h3 id="case-section-exam"><span aria-hidden="true">6</span>专科检查<i>自动带入</i></h3>
                <div className={`case-record-section__readonly ${availablePhysicalExam ? '' : 'is-empty'}`}>
                  {availablePhysicalExam?.findings_text || '尚未进行专科检查，完成体格检查后将自动带入文字结果。'}
                </div>
              </section>

              <section className="case-record-section" aria-labelledby="case-section-diagnosis">
                <label htmlFor="case-diagnosis">
                  <h3 id="case-section-diagnosis"><span aria-hidden="true">7</span>诊断</h3>
                </label>
                <textarea
                  id="case-diagnosis"
                  value={caseDraft.diagnosis}
                  onChange={(event) => updateCaseDraft('diagnosis', event.target.value)}
                  placeholder={isDiagnosisEditable ? '请记录诊断、鉴别诊断及判断依据…' : '进入诊断阶段后填写'}
                  rows={3}
                  readOnly={!isDiagnosisEditable}
                  required={isDiagnosisEditable}
                />
              </section>

              <section className="case-record-section" aria-labelledby="case-section-treatment">
                <label htmlFor="case-treatment">
                  <h3 id="case-section-treatment"><span aria-hidden="true">8</span>处理</h3>
                </label>
                <textarea
                  id="case-treatment"
                  value={caseDraft.treatment}
                  onChange={(event) => updateCaseDraft('treatment', event.target.value)}
                  placeholder={isTreatmentEditable ? '请记录拟申请的检查、处置及治疗计划…' : '进入检查计划阶段后填写'}
                  rows={3}
                  readOnly={!isTreatmentEditable}
                  required={isTreatmentEditable}
                />
              </section>

              <section className="case-record-section" aria-labelledby="case-section-advice">
                <label htmlFor="case-advice">
                  <h3 id="case-section-advice"><span aria-hidden="true">9</span>医嘱</h3>
                </label>
                <textarea
                  id="case-advice"
                  value={caseDraft.medicalAdvice}
                  onChange={(event) => updateCaseDraft('medicalAdvice', event.target.value)}
                  placeholder={isAdviceEditable ? '请记录用药、复诊、饮食及生活方式等医嘱…' : '进入最终诊断阶段后填写'}
                  rows={3}
                  readOnly={!isAdviceEditable}
                  required={isAdviceEditable}
                />
              </section>

              <div className="stage-form__tip">
                <svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>
                <span>提交前请确认内容完整。进入下一阶段后，本阶段答案不可修改。</span>
              </div>
              <button className="button" type="submit" disabled={stageBusy}>
                {stageBusy ? '正在提交…' : session.stage === 'final_reasoning' ? '提交并完成问诊' : '提交并进入下一阶段'}
                {!stageBusy && <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6" /></svg>}
              </button>
            </form>
          </aside>
        )}
      </div>

      {session.status !== 'active' && (
        <section className="feedback-card">
          <h3>{session.status === 'completed' ? '已完成交卷' : '本次作答已超时'}</h3>
          {!feedback ? (
            <button className="button button--secondary" type="button" onClick={loadFeedback} disabled={feedbackBusy}>
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
              {feedback.physical_exam_result && (
                <button className="button button--secondary" type="button" onClick={() => setPhysicalExamOpen(true)}>
                  查看标准体格检查资料
                </button>
              )}
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
      <PhysicalExamDialog
        result={availablePhysicalExam}
        open={physicalExamOpen}
        onClose={() => setPhysicalExamOpen(false)}
      />
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
          <h2 id="student-tasks-title">问诊任务</h2>
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
