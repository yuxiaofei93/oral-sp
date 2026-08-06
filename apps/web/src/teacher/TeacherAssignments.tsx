import { FormEvent, useEffect, useState } from 'react'

import {
  ApiError,
  AssignmentOptions,
  TeacherAssignment,
  closeTeacherAssignment,
  createTeacherAssignment,
  getAssignmentOptions,
  listTeacherAssignments,
  releaseTeacherAssignmentFeedback,
} from '../api/client'
import { TeacherResponses } from './TeacherResponses'

function datetimeLocal(date: Date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

export function TeacherAssignments() {
  const [assignments, setAssignments] = useState<TeacherAssignment[]>([])
  const [options, setOptions] = useState<AssignmentOptions>({ case_versions: [], class_groups: [] })
  const [creating, setCreating] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [reviewing, setReviewing] = useState<TeacherAssignment | null>(null)

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [nextAssignments, nextOptions] = await Promise.all([
        listTeacherAssignments(),
        getAssignmentOptions(),
      ])
      setAssignments(nextAssignments)
      setOptions(nextOptions)
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '考试任务加载失败。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  const availableClasses = options.class_groups.filter((item) => item.student_count > 0)
  const defaultOpen = datetimeLocal(new Date())
  const defaultDeadline = datetimeLocal(new Date(Date.now() + 7 * 24 * 60 * 60 * 1000))

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await createTeacherAssignment({
        title: String(data.get('title') ?? ''),
        case_version_id: String(data.get('case_version_id') ?? ''),
        class_group_id: String(data.get('class_group_id') ?? ''),
        duration_minutes: Number(data.get('duration_minutes')),
        opens_at: new Date(String(data.get('opens_at'))).toISOString(),
        deadline_at: new Date(String(data.get('deadline_at'))).toISOString(),
      })
      form.reset()
      setCreating(false)
      setMessage('考试任务已发布，名单已生成不可变快照。')
      await loadData()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '任务发布失败。')
    } finally {
      setLoading(false)
    }
  }

  async function closeAssignment(assignment: TeacherAssignment) {
    if (!globalThis.confirm('收卷后，仍在作答的学生会立即标记为超时。确定收卷吗？')) return
    setLoading(true)
    setError('')
    try {
      await closeTeacherAssignment(assignment.id)
      setMessage('任务已收卷。确认无误后可以统一发布反馈。')
      await loadData()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '收卷失败。')
    } finally {
      setLoading(false)
    }
  }

  async function releaseFeedback(assignment: TeacherAssignment) {
    if (!globalThis.confirm('发布后学生将看到成绩、评语和标准答案，教师复核也会冻结。确定统一发布反馈吗？')) return
    setLoading(true)
    setError('')
    try {
      await releaseTeacherAssignmentFeedback(assignment.id)
      setMessage('反馈已统一发布。')
      await loadData()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '反馈发布失败。')
    } finally {
      setLoading(false)
    }
  }

  if (reviewing) {
    return (
      <TeacherResponses
        assignment={reviewing}
        onClose={() => {
          setReviewing(null)
          void loadData()
        }}
      />
    )
  }

  return (
    <section className="teacher-workspace" aria-labelledby="teacher-assignments-title">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">EXAM ASSIGNMENTS</p>
          <h2 id="teacher-assignments-title">考试任务</h2>
          <p>选择已发布病例和有学生的班级，为整场问诊设置限时。</p>
        </div>
        <button className="button" type="button" onClick={() => setCreating((value) => !value)}>
          {creating ? '取消发布' : '发布新任务'}
        </button>
      </header>

      {creating && (
        <form className="assignment-form" onSubmit={handleCreate}>
          <label>任务名称<input name="title" placeholder="牙周问诊练习（一）" required /></label>
          <label>病例版本
            <select name="case_version_id" required>
              <option value="">请选择已发布病例</option>
              {options.case_versions.map((item) => <option key={item.id} value={item.id}>{item.case_code} · {item.title} · v{item.version_number}</option>)}
            </select>
          </label>
          <label>班级
            <select name="class_group_id" required>
              <option value="">请选择有学生的班级</option>
              {availableClasses.map((item) => <option key={item.id} value={item.id}>{item.class_code} · {item.class_name}（{item.student_count} 人）</option>)}
            </select>
          </label>
          <label>整场限时（分钟）<input name="duration_minutes" type="number" min="1" max="240" defaultValue="20" required /></label>
          <label>开放时间<input name="opens_at" type="datetime-local" defaultValue={defaultOpen} required /></label>
          <label>最晚截止时间<input name="deadline_at" type="datetime-local" defaultValue={defaultDeadline} required /></label>
          <button className="button" type="submit" disabled={loading || options.case_versions.length === 0 || availableClasses.length === 0}>确认发布任务</button>
          {options.case_versions.length === 0 && <p className="section-help">请先在病例库完成至少一个病例版本发布。</p>}
          {availableClasses.length === 0 && <p className="section-help">请先创建班级并添加至少一名已注册学生。</p>}
        </form>
      )}

      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}
      {loading && assignments.length === 0 && <p className="empty-state">正在加载考试任务…</p>}
      {!loading && assignments.length === 0 && <p className="empty-state">还没有考试任务。</p>}

      <div className="exam-list">
        {assignments.map((assignment) => (
          <article key={assignment.id}>
            <div className="exam-list__header">
              <div><span>{assignment.class_code} · {assignment.class_name}</span><h3>{assignment.title}</h3><p>{assignment.case_title} · v{assignment.case_version_number} · {assignment.duration_minutes} 分钟</p></div>
              <span className={`task-state task-state--${assignment.status}`}>{assignment.status === 'open' ? '进行中' : assignment.feedback_released_at ? '已发布反馈' : '已收卷'}</span>
            </div>
            <div className="progress-grid">
              <div><strong>{assignment.student_count}</strong><span>任务人数</span></div>
              <div><strong>{assignment.not_started_count}</strong><span>未开始</span></div>
              <div><strong>{assignment.active_count}</strong><span>作答中</span></div>
              <div><strong>{assignment.submitted_count}</strong><span>已交卷</span></div>
              <div><strong>{assignment.expired_count}</strong><span>已超时</span></div>
            </div>
            <div className="exam-list__actions">
              <span>截止：{new Date(assignment.deadline_at).toLocaleString('zh-CN')}</span>
              <button className="button button--secondary" type="button" onClick={() => setReviewing(assignment)}>查看学生答卷</button>
              {assignment.status === 'open' && <button className="button button--secondary" type="button" disabled={loading} onClick={() => closeAssignment(assignment)}>统一收卷</button>}
              {assignment.status === 'closed' && !assignment.feedback_released_at && <button className="button" type="button" disabled={loading} onClick={() => releaseFeedback(assignment)}>发布反馈</button>}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
