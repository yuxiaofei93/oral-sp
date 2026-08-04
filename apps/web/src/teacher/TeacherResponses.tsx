import { useEffect, useState } from 'react'

import {
  ApiError,
  TeacherAssignment,
  TeacherResponseRow,
  TeacherSessionRecord,
  getTeacherSessionRecord,
  listTeacherResponses,
} from '../api/client'

const attemptNames = {
  not_started: '未开始',
  active: '作答中',
  completed: '已交卷',
  expired: '已超时',
}

const submissionNames: Record<string, string> = {
  history_summary: '病史摘要',
  initial_reasoning: '初步诊断与鉴别诊断',
  test_selection: '检查计划',
  final_reasoning: '最终诊断与处理原则',
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

export function TeacherResponses({
  assignment,
  onClose,
}: {
  assignment: TeacherAssignment
  onClose: () => void
}) {
  const [rows, setRows] = useState<TeacherResponseRow[]>([])
  const [record, setRecord] = useState<TeacherSessionRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    listTeacherResponses(assignment.id)
      .then(setRows)
      .catch((requestError: unknown) => {
        setError(requestError instanceof ApiError ? requestError.message : '学生答卷列表加载失败。')
      })
      .finally(() => setLoading(false))
  }, [assignment.id])

  async function openRecord(sessionId: string) {
    setLoading(true)
    setError('')
    try {
      setRecord(await getTeacherSessionRecord(sessionId))
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '学生答卷加载失败。')
    } finally {
      setLoading(false)
    }
  }

  if (record) {
    return (
      <section className="teacher-workspace response-record" aria-labelledby="student-record-title">
        <header className="workspace-header">
          <div>
            <button className="text-button" type="button" onClick={() => setRecord(null)}>← 返回答卷列表</button>
            <h2 id="student-record-title">{record.student_name}的答卷</h2>
            <p>{record.student_phone} · {attemptNames[record.status]}</p>
          </div>
          {record.assessment && (
            <div className="record-score">
              <strong>{record.assessment.automatic_score}</strong>
              <span>/ {record.assessment.scored_maximum}</span>
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
                <span>{message.role === 'student' ? '学生' : '患者'} · #{message.sequence}</span>
                <p>{message.content}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="record-section">
          <h3>阶段提交</h3>
          <div className="submission-records">
            {record.submissions.map((submission) => (
              <article key={submission.id}>
                <strong>{submissionNames[submission.submission_type] ?? submission.submission_type}</strong>
                <pre>{JSON.stringify(submission.payload, null, 2)}</pre>
              </article>
            ))}
          </div>
        </section>

        {record.assessment && (
          <section className="record-section">
            <h3>自动评分与证据</h3>
            <p>{record.assessment.feedback_summary}</p>
            <div className="score-evidence-list">
              {record.assessment.scoring_items.map((item) => (
                <article key={item.code}>
                  <header><div><strong>{item.label}</strong><span>{decisionNames[item.decision]}</span></div><b>{item.automatic_score === null ? '—' : item.automatic_score} / {item.max_score}</b></header>
                  <p>{item.reason}</p>
                  {item.evidence_excerpt && <pre>{item.evidence_excerpt}</pre>}
                  {item.standard_answer && <small>标准答案：{item.standard_answer}</small>}
                </article>
              ))}
            </div>
          </section>
        )}

        <section className="record-section standard-reference">
          <h3>病例标准答案</h3>
          <h4>标准诊断</h4>
          {record.standard_diagnoses.map((item) => <p key={`${item.type}-${item.name}`}>{item.name}：{item.supporting_evidence.join('、')}</p>)}
          <h4>标准检查</h4>
          {record.standard_tests.map((item) => <p key={item.code}>{item.name}：{item.result}（{item.interpretation}）</p>)}
        </section>
      </section>
    )
  }

  return (
    <section className="teacher-workspace" aria-labelledby="assignment-responses-title">
      <header className="workspace-header">
        <div>
          <button className="text-button" type="button" onClick={onClose}>← 返回考试任务</button>
          <h2 id="assignment-responses-title">{assignment.title}答卷</h2>
          <p>{assignment.course_name} / {assignment.class_name} · {assignment.student_count} 人</p>
        </div>
      </header>
      {error && <p className="form-error">{error}</p>}
      {loading && rows.length === 0 && <p className="empty-state">正在加载学生答卷…</p>}
      <div className="response-table-wrap">
        <table className="response-table">
          <thead><tr><th>学生</th><th>状态</th><th>用时</th><th>自动得分</th><th /></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.student_id}>
                <td><strong>{row.display_name}</strong><small>{row.phone}</small></td>
                <td>{attemptNames[row.attempt_status]}</td>
                <td>{elapsed(row.elapsed_seconds)}</td>
                <td>{row.score ? `${row.score.automatic_score} / ${row.score.scored_maximum}` : '—'}</td>
                <td><button className="text-button" type="button" disabled={!row.session_id || loading} onClick={() => row.session_id && openRecord(row.session_id)}>查看答卷</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
