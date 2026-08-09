import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'

import {
  ApiError,
  SessionFeedback,
  SimulationSession,
  StudentCaseDraft,
  StudentAssignment,
  askPatient,
  completeStudentSession,
  getSessionFeedback,
  getStudentSession,
  listStudentAssignments,
  saveStudentCaseDraft,
  startStudentSession,
} from '../api/client'
import { PhysicalExamDialog } from '../PhysicalExamDialog'

const difficultyNames = { basic: '基础', intermediate: '中级', advanced: '高级' }
const attemptNames = {
  not_started: '未开始',
  active: '作答中',
  completed: '已交卷',
  expired: '已超时',
}
const AUTO_SAVE_DELAY_MS = 500
const editableFieldNames: Array<[keyof CaseDraft, string]> = [
  ['chiefComplaint', '主诉'],
  ['presentIllness', '现病史'],
  ['pastHistory', '既往史'],
  ['familyHistory', '家族史'],
  ['diagnosis', '诊断'],
  ['treatment', '处理'],
  ['medicalAdvice', '医嘱'],
]
type SaveStatus = 'saved' | 'dirty' | 'saving' | 'error'

type CaseDraft = {
  chiefComplaint: string
  presentIllness: string
  pastHistory: string
  familyHistory: string
  diagnosis: string
  treatment: string
  medicalAdvice: string
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

function fromApiCaseDraft(source?: Partial<StudentCaseDraft> | null): CaseDraft {
  return {
    chiefComplaint: source?.chief_complaint ?? '',
    presentIllness: source?.present_illness ?? '',
    pastHistory: source?.past_history ?? '',
    familyHistory: source?.family_history ?? '',
    diagnosis: source?.diagnosis ?? '',
    treatment: source?.treatment ?? '',
    medicalAdvice: source?.medical_advice ?? '',
  }
}

function toApiCaseDraft(source: CaseDraft): StudentCaseDraft {
  return {
    chief_complaint: source.chiefComplaint,
    present_illness: source.presentIllness,
    past_history: source.pastHistory,
    family_history: source.familyHistory,
    diagnosis: source.diagnosis,
    treatment: source.treatment,
    medical_advice: source.medicalAdvice,
  }
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

function Workbench({ initialSession, onExit }: { initialSession: SimulationSession; onExit: () => void }) {
  const initialCaseDraft = fromApiCaseDraft(initialSession.case_record ?? initialSession.case_draft)
  const [session, setSession] = useState(initialSession)
  const [remaining, setRemaining] = useState(initialSession.remaining_seconds)
  const [question, setQuestion] = useState('')
  const [pendingQuestion, setPendingQuestion] = useState<{ content: string; id: string } | null>(null)
  const [caseDraft, setCaseDraft] = useState<CaseDraft>(initialCaseDraft)
  const [draftRevision, setDraftRevision] = useState(0)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('saved')
  const [saveError, setSaveError] = useState('')
  const [blankFields, setBlankFields] = useState<string[] | null>(null)
  const [feedback, setFeedback] = useState<SessionFeedback | null>(null)
  const [physicalExamOpen, setPhysicalExamOpen] = useState(false)
  const [questionBusy, setQuestionBusy] = useState(false)
  const [completionBusy, setCompletionBusy] = useState(false)
  const [feedbackBusy, setFeedbackBusy] = useState(false)
  const [error, setError] = useState('')
  const conversationRef = useRef<HTMLDivElement>(null)
  const draftRef = useRef(initialCaseDraft)
  const localRevisionRef = useRef(0)
  const savedRevisionRef = useRef(0)
  const serverRevisionRef = useRef(initialSession.case_draft_revision)
  const saveInFlightRef = useRef<Promise<boolean> | null>(null)
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

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

  async function persistLatestDraft(): Promise<boolean> {
    if (session.status !== 'active') return true
    if (saveInFlightRef.current) {
      const result = await saveInFlightRef.current
      if (savedRevisionRef.current < localRevisionRef.current) return persistLatestDraft()
      return result
    }
    if (savedRevisionRef.current >= localRevisionRef.current) return true

    const operation = (async () => {
      setSaveError('')
      while (savedRevisionRef.current < localRevisionRef.current) {
        setSaveStatus('saving')
        const snapshot = draftRef.current
        const snapshotRevision = localRevisionRef.current
        try {
          const updated = await saveStudentCaseDraft(session.id, {
            expected_revision: serverRevisionRef.current,
            case_draft: toApiCaseDraft(snapshot),
          })
          serverRevisionRef.current = updated.case_draft_revision
          savedRevisionRef.current = snapshotRevision
          setSession((current) => ({
            ...current,
            case_draft: updated.case_draft,
            case_draft_revision: updated.case_draft_revision,
          }))
        } catch (requestError: unknown) {
          setSaveStatus('error')
          setSaveError(
            requestError instanceof ApiError
              ? requestError.message
              : '自动保存失败，请检查网络后重试。',
          )
          return false
        }
      }
      setSaveStatus('saved')
      return true
    })()

    saveInFlightRef.current = operation
    try {
      return await operation
    } finally {
      if (saveInFlightRef.current === operation) saveInFlightRef.current = null
    }
  }

  useEffect(() => {
    if (
      session.status !== 'active'
      || draftRevision === 0
      || savedRevisionRef.current >= draftRevision
    ) return undefined
    const timer = globalThis.setTimeout(() => {
      autoSaveTimerRef.current = null
      void persistLatestDraft()
    }, AUTO_SAVE_DELAY_MS)
    autoSaveTimerRef.current = timer
    return () => {
      globalThis.clearTimeout(timer)
      if (autoSaveTimerRef.current === timer) autoSaveTimerRef.current = null
    }
  }, [draftRevision, session.status])

  function clearAutoSaveTimer() {
    if (!autoSaveTimerRef.current) return
    globalThis.clearTimeout(autoSaveTimerRef.current)
    autoSaveTimerRef.current = null
  }

  function updateCaseDraft(field: keyof CaseDraft, value: string) {
    if (session.status !== 'active') return
    const updated = { ...draftRef.current, [field]: value }
    const nextRevision = localRevisionRef.current + 1
    draftRef.current = updated
    localRevisionRef.current = nextRevision
    setCaseDraft(updated)
    setDraftRevision(nextRevision)
    setSaveStatus('dirty')
    setSaveError('')
  }

  async function handleExit() {
    clearAutoSaveTimer()
    if (await persistLatestDraft()) onExit()
  }

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

  async function finalizeSession() {
    clearAutoSaveTimer()
    if (!(await persistLatestDraft())) return
    setCompletionBusy(true)
    setError('')
    try {
      const result = await completeStudentSession(session.id, {
        expected_revision: serverRevisionRef.current,
        case_record: toApiCaseDraft(draftRef.current),
      })
      serverRevisionRef.current = result.session.case_draft_revision
      setSession(result.session)
      setRemaining(result.session.remaining_seconds)
      setSaveStatus('saved')
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '交卷失败，请稍后重试。')
    } finally {
      setCompletionBusy(false)
    }
  }

  function handleCaseSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (session.status !== 'active') return
    const missing = editableFieldNames
      .filter(([field]) => !draftRef.current[field].trim())
      .map(([, label]) => label)
    if (missing.length > 0) {
      setBlankFields(missing)
      return
    }
    void finalizeSession()
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

  const patientName = session.patient_name || '标准化患者'
  const availablePhysicalExam = session.physical_exam_result ?? feedback?.physical_exam_result ?? null
  const caseEditable = session.status === 'active'
  const specialtyExamText = session.case_record?.specialty_exam || availablePhysicalExam?.findings_text || ''
  const saveStatusText = session.status === 'completed'
    ? '已交卷'
    : session.status === 'expired'
      ? '已超时'
      : saveStatus === 'dirty'
        ? '未保存'
        : saveStatus === 'saving'
          ? '保存中…'
          : saveStatus === 'error'
            ? '保存失败'
            : '已保存'

  return (
    <section className="student-workbench" aria-labelledby="workbench-title">
      <header className="workbench-header">
        <div className="workbench-header__identity">
          <button className="workbench-back" type="button" onClick={() => void handleExit()} aria-label="返回任务列表">
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

      <div className="exam-notice">
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path d="M12 8v4.5M12 16h.01" />
          <circle cx="12" cy="12" r="9" />
        </svg>
        <span>整场任务限时，病例内容会自动保存；问题发送和最终交卷后将自动留痕，无法修改或删除。</span>
      </div>
      {error && <p className="form-error workbench-error" role="alert">{error}</p>}

      <div className="workbench-layout">
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

          {session.status === 'active' ? (
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
          ) : null}
        </section>

          <aside className="clinical-panel" aria-labelledby="case-editor-title">
            <div className="clinical-panel__heading">
              <span id="case-editor-title">病例编辑</span>
              <div className={`case-save-status is-${session.status === 'active' ? saveStatus : 'saved'}`}>
                <b>{saveStatusText}</b>
                {session.status === 'active' && saveStatus === 'error' && (
                  <button type="button" onClick={() => void persistLatestDraft()}>重试</button>
                )}
              </div>
            </div>
            <form className="case-record-form" onSubmit={handleCaseSubmit}>
              {saveError && <p className="case-save-error" role="alert">{saveError}</p>}

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
                  placeholder={caseEditable ? '请用一段文字记录患者此次就诊的主要症状及持续时间…' : '未填写'}
                  rows={2}
                  maxLength={4000}
                  readOnly={!caseEditable}
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
                  placeholder={caseEditable ? '请记录本次疾病的发生、发展及诊疗经过…' : '未填写'}
                  rows={2}
                  maxLength={4000}
                  readOnly={!caseEditable}
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
                  placeholder={caseEditable ? '请记录既往疾病、手术、过敏及用药等情况…' : '未填写'}
                  rows={2}
                  maxLength={4000}
                  readOnly={!caseEditable}
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
                  placeholder={caseEditable ? '请记录家族中相关疾病及遗传病史…' : '未填写'}
                  rows={2}
                  maxLength={4000}
                  readOnly={!caseEditable}
                />
              </section>

              <section className="case-record-section" aria-labelledby="case-section-exam">
                <h3 id="case-section-exam"><span aria-hidden="true">6</span>专科检查<i>自动带入</i></h3>
                <div className={`case-record-section__readonly ${specialtyExamText ? '' : 'is-empty'}`}>
                  {specialtyExamText || '尚未进行专科检查，完成体格检查后将自动带入文字结果。'}
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
                  placeholder={caseEditable ? '请记录诊断、鉴别诊断及判断依据…' : '未填写'}
                  rows={2}
                  maxLength={4000}
                  readOnly={!caseEditable}
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
                  placeholder={caseEditable ? '请记录拟申请的检查、处置及治疗计划…' : '未填写'}
                  rows={2}
                  maxLength={4000}
                  readOnly={!caseEditable}
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
                  placeholder={caseEditable ? '请记录用药、复诊、饮食及生活方式等医嘱…' : '未填写'}
                  rows={2}
                  maxLength={4000}
                  readOnly={!caseEditable}
                />
              </section>

              {session.status === 'active' && (
                <>
                  <div className="case-record-form__tip">
                    <svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>
                    <span>病例会自动保存。最终交卷后，病例内容和问诊记录均不可修改。</span>
                  </div>
                  <button className="button" type="submit" disabled={completionBusy}>
                    {completionBusy ? '正在交卷…' : '提交并完成问诊'}
                    {!completionBusy && <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6" /></svg>}
                  </button>
                </>
              )}
            </form>
          </aside>
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
      {blankFields && (
        <div className="case-submit-dialog__backdrop">
          <section className="case-submit-dialog" role="dialog" aria-modal="true" aria-labelledby="blank-fields-title">
            <span>确认交卷</span>
            <h2 id="blank-fields-title">以下内容尚未填写</h2>
            <p>{blankFields.join('、')}</p>
            <small>留空不会阻止交卷，但提交后将无法补充或修改。</small>
            <div>
              <button className="button button--secondary" type="button" onClick={() => setBlankFields(null)}>
                返回补充
              </button>
              <button
                className="button"
                type="button"
                onClick={() => {
                  setBlankFields(null)
                  void finalizeSession()
                }}
              >
                仍然提交
              </button>
            </div>
          </section>
        </div>
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
