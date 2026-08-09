import { type FormEvent, useEffect, useState } from 'react'

import {
  ApiError,
  AssignmentStatistics,
  TeacherAssignment,
  TeacherResponseRow,
  TeacherSessionRecord,
  getTeacherSessionRecord,
  getTeacherAssignmentStatistics,
  listTeacherResponses,
  runTeacherAIEvaluation,
  saveTeacherReview,
  teacherAssignmentCsvUrl,
} from '../api/client'
import { PhysicalExamDialog } from '../PhysicalExamDialog'

const attemptNames = {
  not_started: '未开始',
  active: '作答中',
  completed: '已交卷',
  expired: '已超时',
}

const decisionNames = {
  achieved: '已完成',
  partial: '部分完成',
  missed: '未完成',
  pending: '待评价',
}

function elapsed(seconds: number | null) {
  if (seconds === null) return '—'
  const minutes = Math.floor(seconds / 60)
  return `${minutes} 分 ${seconds % 60} 秒`
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

export function TeacherResponses({
  assignment,
  onClose,
}: {
  assignment: TeacherAssignment
  onClose: () => void
}) {
  const [rows, setRows] = useState<TeacherResponseRow[]>([])
  const [statistics, setStatistics] = useState<AssignmentStatistics | null>(null)
  const [record, setRecord] = useState<TeacherSessionRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [evaluatingAI, setEvaluatingAI] = useState(false)
  const [savingReview, setSavingReview] = useState(false)
  const [error, setError] = useState('')
  const [reviewScores, setReviewScores] = useState<Record<string, string>>({})
  const [reviewReasons, setReviewReasons] = useState<Record<string, string>>({})
  const [teacherComment, setTeacherComment] = useState('')
  const [physicalExamOpen, setPhysicalExamOpen] = useState(false)

  useEffect(() => {
    Promise.all([
      listTeacherResponses(assignment.id),
      getTeacherAssignmentStatistics(assignment.id),
    ])
      .then(([nextRows, nextStatistics]) => {
        setRows(nextRows)
        setStatistics(nextStatistics)
      })
      .catch((requestError: unknown) => {
        setError(requestError instanceof ApiError ? requestError.message : '学生答卷列表加载失败。')
      })
      .finally(() => setLoading(false))
  }, [assignment.id])

  function loadReviewDraft(nextRecord: TeacherSessionRecord) {
    const scores: Record<string, string> = {}
    const reasons: Record<string, string> = {}
    nextRecord.assessment?.scoring_items.forEach((item) => {
      scores[item.code] = item.effective_score === null ? '' : String(item.effective_score)
      reasons[item.code] = item.adjustment_reason
    })
    setReviewScores(scores)
    setReviewReasons(reasons)
    setTeacherComment(nextRecord.latest_review?.comment ?? '')
  }

  async function openRecord(sessionId: string) {
    setLoading(true)
    setError('')
    try {
      const nextRecord = await getTeacherSessionRecord(sessionId)
      setRecord(nextRecord)
      loadReviewDraft(nextRecord)
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '学生答卷加载失败。')
    } finally {
      setLoading(false)
    }
  }

  async function submitReview(event: FormEvent) {
    event.preventDefault()
    if (!record?.assessment) return
    const scores: Array<{ code: string; score: number | null; reason: string }> = []
    for (const item of record.assessment.scoring_items) {
      const rawValue = reviewScores[item.code]?.trim() ?? ''
      const parsedValue = rawValue === '' ? null : Number(rawValue)
      const hadOverride = Boolean(record.latest_review?.score_overrides[item.code])
      const baseScore = item.ai_score ?? item.automatic_score
      const differsFromBase = parsedValue !== baseScore
      if (!hadOverride && !differsFromBase) continue
      const reason = reviewReasons[item.code]?.trim() ?? ''
      if (!reason) {
        setError(`调整“${item.label}”时必须填写理由。`)
        return
      }
      scores.push({ code: item.code, score: parsedValue, reason })
    }
    setSavingReview(true)
    setError('')
    try {
      await saveTeacherReview(record.id, { comment: teacherComment, scores })
      const [nextRecord, nextRows, nextStatistics] = await Promise.all([
        getTeacherSessionRecord(record.id),
        listTeacherResponses(assignment.id),
        getTeacherAssignmentStatistics(assignment.id),
      ])
      setRecord(nextRecord)
      setRows(nextRows)
      setStatistics(nextStatistics)
      loadReviewDraft(nextRecord)
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '教师复核保存失败。')
    } finally {
      setSavingReview(false)
    }
  }

  async function evaluateWithAI() {
    if (!record) return
    const hasSuccessfulAI = record.assessment?.scoring_items.some((item) => item.ai_score !== null)
    const force = record.ai_evaluation?.status === 'succeeded' || Boolean(hasSuccessfulAI)
    if (force && !globalThis.confirm('将重新调用 DeepSeek 并生成一版新的 AI 辅助评价，是否继续？')) return
    setEvaluatingAI(true)
    setError('')
    try {
      await runTeacherAIEvaluation(record.id, force)
      const [nextRecord, nextRows, nextStatistics] = await Promise.all([
        getTeacherSessionRecord(record.id),
        listTeacherResponses(assignment.id),
        getTeacherAssignmentStatistics(assignment.id),
      ])
      setRecord(nextRecord)
      setRows(nextRows)
      setStatistics(nextStatistics)
      loadReviewDraft(nextRecord)
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : 'AI 辅助评价生成失败。')
    } finally {
      setEvaluatingAI(false)
    }
  }

  if (record) {
    return (
      <section className="teacher-workspace response-record" aria-labelledby="student-record-title">
        <header className="workspace-header">
          <div>
            <button className="text-button" type="button" onClick={() => setRecord(null)}>← 返回答卷列表</button>
            <h2 id="student-record-title">{record.student_name}的答卷</h2>
            <p>{record.student_email} · {attemptNames[record.status]}</p>
          </div>
          {record.assessment && (
            <div className="record-score">
              <strong>{record.assessment.final_score}</strong>
              <span>/ {record.assessment.scored_maximum}</span>
              {record.assessment.final_score !== record.assessment.automatic_score && <small>自动得分 {record.assessment.automatic_score}</small>}
              {record.assessment.provisional && <small>含待评价项，总分 {record.assessment.maximum_score}</small>}
            </div>
          )}
        </header>
        {error && <p className="form-error">{error}</p>}

        <section className="record-section">
          <h3>完整问诊记录</h3>
          <div className="conversation">
            <article className="message message--patient"><span>患者开场白</span><p>{record.opening_statement}</p></article>
            {record.messages.map((message) => (
              <article className={`message message--${message.role}`} key={message.id}>
                <span>{message.role === 'student' ? '学生' : message.role === 'system' ? '系统 · 体格检查' : '患者'} · #{message.sequence}</span>
                <p>{message.content}</p>
                {message.kind === 'physical_exam_result' && record.physical_exam_result && (
                  <button className="physical-exam-message-link" type="button" onClick={() => setPhysicalExamOpen(true)}>
                    查看完整体格检查资料
                  </button>
                )}
              </article>
            ))}
          </div>
        </section>

        <section className="record-section">
          <h3>病例记录</h3>
          <div className="case-record-review">
            <article className="case-record-review__identity">
              <h4>基本信息</h4>
              <dl>
                <div><dt>患者化名</dt><dd>{record.patient_name}</dd></div>
                <div><dt>科室</dt><dd>口腔粘膜科</dd></div>
                <div><dt>就诊日期</dt><dd>{visitDate(record.started_at)}</dd></div>
                <div><dt>流水号</dt><dd>{recordNumber(record.id)}</dd></div>
              </dl>
            </article>
            {[
              ['主诉', record.case_record?.chief_complaint ?? record.case_draft?.chief_complaint ?? ''],
              ['现病史', record.case_record?.present_illness ?? record.case_draft?.present_illness ?? ''],
              ['既往史', record.case_record?.past_history ?? record.case_draft?.past_history ?? ''],
              ['家族史', record.case_record?.family_history ?? record.case_draft?.family_history ?? ''],
              ['专科检查', record.case_record?.specialty_exam ?? record.physical_exam_result?.findings_text ?? ''],
              ['诊断', record.case_record?.diagnosis ?? record.case_draft?.diagnosis ?? ''],
              ['处理', record.case_record?.treatment ?? record.case_draft?.treatment ?? ''],
              ['医嘱', record.case_record?.medical_advice ?? record.case_draft?.medical_advice ?? ''],
            ].map(([label, value]) => (
              <article key={label}>
                <h4>{label}</h4>
                <p className={value ? '' : 'is-empty'}>{value || '未填写'}</p>
              </article>
            ))}
          </div>
        </section>

        {record.assessment && (
          <section className="record-section">
            <h3>评分与证据</h3>
            <p>{record.assessment.feedback_summary}</p>
            <div className="score-evidence-list">
              {record.assessment.scoring_items.map((item) => (
                <article key={item.code}>
                  <header><div><strong>{item.label}</strong><span>{decisionNames[item.effective_decision]}</span></div><b>{item.effective_score === null ? '—' : item.effective_score} / {item.max_score}</b></header>
                  {item.teacher_score !== null && <small>评价基准 {item.ai_score ?? item.automatic_score ?? '待评价'}；教师复核 {item.teacher_score}</small>}
                  {item.adjustment_reason && <p>复核理由：{item.adjustment_reason}</p>}
                  <p>{item.reason}</p>
                  {item.evidence_excerpt && <pre>{item.evidence_excerpt}</pre>}
                  {item.ai_score !== null && (
                    <div className="ai-score-evidence">
                      <small>AI 辅助评分：{item.ai_score} / {item.max_score} · 置信度 {Math.round((item.ai_confidence ?? 0) * 100)}%</small>
                      {item.ai_reason && <p>AI 评分理由：{item.ai_reason}</p>}
                      {item.ai_evidence_excerpt && <pre>{item.ai_evidence_excerpt}</pre>}
                      {item.ai_feedback && <p>AI 改进建议：{item.ai_feedback}</p>}
                    </div>
                  )}
                  {item.standard_answer && <small>标准答案：{item.standard_answer}</small>}
                </article>
              ))}
            </div>
          </section>
        )}

        {record.assessment?.scoring_items.some((item) => item.evaluation_method === 'ai') && (
          <section className="record-section ai-evaluation-panel">
            <div>
              <h3>AI 辅助评价</h3>
              <p>由 DeepSeek 按病例评分标准分析问诊记录和病例记录；最终成绩仍可由教师复核。</p>
            </div>
            {record.ai_evaluation ? (
              <div className={`ai-run-status ai-run-status--${record.ai_evaluation.status}`}>
                <strong>{record.ai_evaluation.status === 'succeeded' ? '评价已生成' : record.ai_evaluation.status === 'running' ? '正在评价' : '最近一次评价失败'}</strong>
                <span>{record.ai_evaluation.provider} / {record.ai_evaluation.resolved_model || record.ai_evaluation.model}</span>
                <span>触发教师：{record.ai_evaluation.requested_by_name}</span>
                {record.ai_evaluation.status === 'succeeded' && <span>耗时 {record.ai_evaluation.latency_ms} ms · 输入 {record.ai_evaluation.input_tokens ?? '—'} / 输出 {record.ai_evaluation.output_tokens ?? '—'} tokens</span>}
                {record.ai_evaluation.feedback_summary && <p>{record.ai_evaluation.feedback_summary}</p>}
                {record.ai_evaluation.error_code && <span>错误代码：{record.ai_evaluation.error_code}</span>}
              </div>
            ) : (
              <p className="muted-copy">尚未生成 AI 辅助评价。</p>
            )}
            {assignment.feedback_released_at ? (
              <p className="review-frozen">反馈已发布，AI 评价已经冻结。</p>
            ) : (
              <button
                className="button button--secondary"
                type="button"
                disabled={evaluatingAI || record.ai_evaluation?.status === 'running'}
                onClick={evaluateWithAI}
              >
                {evaluatingAI
                  ? 'DeepSeek 评价中…'
                  : record.assessment.scoring_items.some((item) => item.ai_score !== null)
                    ? '重新生成 AI 评价'
                    : record.ai_evaluation?.status === 'failed'
                      ? '重试 AI 评价'
                      : '生成 AI 辅助评价'}
              </button>
            )}
          </section>
        )}

        {record.assessment && record.status !== 'active' && (
          <section className="record-section teacher-review">
            <h3>教师复核与评语</h3>
            {record.latest_review && <p>当前为第 {record.latest_review.revision} 版复核，由 {record.latest_review.reviewer_name} 于 {new Date(record.latest_review.created_at).toLocaleString()} 保存。</p>}
            {assignment.feedback_released_at ? (
              <p className="review-frozen">反馈已发布，复核成绩和评语已经冻结。</p>
            ) : (
              <form onSubmit={submitReview}>
                <div className="review-score-grid">
                  {record.assessment.scoring_items.map((item) => (
                    <article key={item.code}>
                      <div><strong>{item.label}</strong><small>{item.ai_score !== null ? 'AI 辅助' : '规则评分'}：{item.ai_score ?? item.automatic_score ?? '待评价'} / {item.max_score}</small></div>
                      <label>
                        复核分数
                        <input
                          type="number"
                          min="0"
                          max={item.max_score}
                          step="0.5"
                          value={reviewScores[item.code] ?? ''}
                          onChange={(event) => setReviewScores((current) => ({ ...current, [item.code]: event.target.value }))}
                        />
                      </label>
                      <label>
                        改分理由（改分时必填）
                        <input
                          value={reviewReasons[item.code] ?? ''}
                          onChange={(event) => setReviewReasons((current) => ({ ...current, [item.code]: event.target.value }))}
                          placeholder="说明复核依据"
                        />
                      </label>
                    </article>
                  ))}
                </div>
                <label>
                  教师评语
                  <textarea rows={4} value={teacherComment} onChange={(event) => setTeacherComment(event.target.value)} placeholder="反馈发布后学生可见" />
                </label>
                <button className="primary-button" type="submit" disabled={savingReview}>{savingReview ? '保存中…' : '保存复核版本'}</button>
              </form>
            )}
          </section>
        )}

        <section className="record-section standard-reference">
          <h3>病例标准答案</h3>
          <h4>标准诊断</h4>
          {record.standard_diagnoses.map((item) => <p key={`${item.type}-${item.name}`}>{item.name}：{item.supporting_evidence.join('、')}</p>)}
          <h4>标准检查</h4>
          {record.standard_tests.map((item) => <p key={item.code}>{item.name}：{item.result}（{item.interpretation}）</p>)}
          {record.physical_exam_result && (
            <button className="button button--secondary" type="button" onClick={() => setPhysicalExamOpen(true)}>
              查看口腔体格检查资料
            </button>
          )}
        </section>
        <PhysicalExamDialog
          result={record.physical_exam_result}
          open={physicalExamOpen}
          onClose={() => setPhysicalExamOpen(false)}
        />
      </section>
    )
  }

  return (
    <section className="teacher-workspace" aria-labelledby="assignment-responses-title">
      <header className="workspace-header">
        <div>
          <button className="text-button" type="button" onClick={onClose}>← 返回问诊任务</button>
          <h2 id="assignment-responses-title">{assignment.title}答卷</h2>
          <p>{assignment.class_name} · {assignment.student_count} 人</p>
        </div>
        <a className="button button--secondary" href={teacherAssignmentCsvUrl(assignment.id)}>导出 CSV</a>
      </header>
      {error && <p className="form-error">{error}</p>}
      {loading && rows.length === 0 && <p className="empty-state">正在加载学生答卷…</p>}
      {statistics && (
        <section className="assignment-statistics" aria-label="班级统计">
          <div className="statistics-summary">
            <article><strong>{statistics.summary.completion_rate}%</strong><span>完成率（{statistics.summary.completed_count}/{statistics.summary.student_count}）</span></article>
            <article><strong>{statistics.summary.average_score_percentage === null ? '—' : `${statistics.summary.average_score_percentage}%`}</strong><span>平均得分率</span></article>
            <article><strong>{statistics.summary.average_score ?? '—'}</strong><span>平均当前得分</span></article>
            <article><strong>{elapsed(statistics.summary.average_duration_seconds)}</strong><span>平均用时</span></article>
            <article><strong>{statistics.summary.assessed_count}</strong><span>已生成评分</span></article>
          </div>
          <div className="statistics-issues">
            <article>
              <h3>高频遗漏</h3>
              {statistics.frequent_omissions.length === 0 ? <p>暂无遗漏数据</p> : statistics.frequent_omissions.map((item) => <p key={item.code}>{item.label}<span>{item.count} 人 · {item.rate}%</span></p>)}
            </article>
            <article>
              <h3>常见错误</h3>
              {statistics.common_errors.length === 0 ? <p>暂无错误数据</p> : statistics.common_errors.map((item) => <p key={item.code}>{item.label}<span>{item.count} 人 · {item.rate}%</span></p>)}
            </article>
          </div>
        </section>
      )}
      <div className="response-table-wrap">
        <table className="response-table">
          <thead><tr><th>学生</th><th>状态</th><th>用时</th><th>当前得分</th><th /></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.student_id}>
                <td><strong>{row.display_name}</strong><small>{row.email}</small></td>
                <td>{attemptNames[row.attempt_status]}</td>
                <td>{elapsed(row.elapsed_seconds)}</td>
                <td>{row.score ? `${row.score.final_score} / ${row.score.scored_maximum}` : '—'}</td>
                <td><button className="text-button" type="button" disabled={!row.session_id || loading} onClick={() => row.session_id && openRecord(row.session_id)}>查看答卷</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
