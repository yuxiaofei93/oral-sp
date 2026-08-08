import { FormEvent, useEffect, useState } from 'react'

import {
  ApiError,
  TeachingClass,
  createTeachingClass,
  listTeachingClasses,
  setTeachingClassActive,
} from '../api/client'

export function ClassManagement() {
  const [classes, setClasses] = useState<TeachingClass[]>([])
  const [creating, setCreating] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      setClasses(await listTeachingClasses())
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '班级列表加载失败。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await createTeachingClass({ name: String(data.get('name') ?? '').trim() })
      form.reset()
      setCreating(false)
      setMessage('班级已创建，学生注册时可以选择该班级。')
      await loadData()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '班级创建失败。')
    } finally {
      setLoading(false)
    }
  }

  async function handleClassStatus(classGroup: TeachingClass) {
    const nextActive = !classGroup.is_active
    const confirmed = globalThis.confirm(nextActive
      ? `确定恢复班级“${classGroup.name}”吗？恢复后可用于学生注册、调班和发布新任务。`
      : `确定删除班级“${classGroup.name}”吗？已有学员、任务和答卷会保留。`)
    if (!confirmed) return
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await setTeachingClassActive(classGroup.id, nextActive)
      setMessage(nextActive
        ? `班级“${classGroup.name}”已恢复。`
        : `班级“${classGroup.name}”已删除，历史记录保持不变。`)
      await loadData()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '班级状态更新失败。')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="teacher-workspace" aria-labelledby="class-management-title">
      <header className="workspace-header">
        <div>
          <h2 id="class-management-title">班级管理</h2>
        </div>
        <button
          className="button"
          type="button"
          disabled={loading}
          onClick={() => {
            setCreating(true)
            setError('')
            setMessage('')
          }}
        >
          创建班级
        </button>
      </header>

      {!creating && error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}
      {loading && classes.length === 0 && <p className="empty-state">正在加载班级…</p>}
      {!loading && classes.length === 0 && <p className="empty-state">目前没有班级。</p>}

      <div className="class-list">
        {classes.map((classGroup) => (
          <article
            className={classGroup.is_active ? undefined : 'class-list__item--inactive'}
            key={classGroup.id}
          >
            <header className="class-list__header">
              <div>
                <div className="class-list__identity">
                  <h3>{classGroup.name}</h3>
                  <span className={`class-status ${classGroup.is_active ? '' : 'class-status--inactive'}`}>
                    {classGroup.is_active ? '正常' : '已删除'}
                  </span>
                </div>
                <p>{classGroup.student_count} 名学员</p>
              </div>
              <button
                className={`text-button ${classGroup.is_active ? 'text-button--danger' : ''}`}
                type="button"
                disabled={loading}
                onClick={() => handleClassStatus(classGroup)}
              >
                {classGroup.is_active ? '删除班级' : '恢复班级'}
              </button>
            </header>
          </article>
        ))}
      </div>

      {creating && (
        <div className="confirmation-overlay">
          <section
            className="confirmation-dialog class-create-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="class-create-title"
          >
            <h2 id="class-create-title">创建班级</h2>
            <form onSubmit={handleCreate}>
              <label>
                班级名称
                <input name="name" autoFocus required maxLength={120} />
              </label>
              {error && <p className="form-error">{error}</p>}
              <div className="confirmation-dialog__actions">
                <button
                  className="button button--secondary"
                  type="button"
                  disabled={loading}
                  onClick={() => {
                    setCreating(false)
                    setError('')
                  }}
                >
                  取消
                </button>
                <button className="button" type="submit" disabled={loading}>
                  {loading ? '创建中…' : '确认创建'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </section>
  )
}
