import { FormEvent, useEffect, useMemo, useState } from 'react'

import {
  ApiError,
  TeachingClass,
  createTeachingClass,
  deleteTeachingClass,
  listTeachingClasses,
  removeClassStudent,
} from '../api/client'

export function ClassManagement() {
  const [classes, setClasses] = useState<TeachingClass[]>([])
  const [selectedClassId, setSelectedClassId] = useState('')
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

  const selectedClass = useMemo(
    () => classes.find((item) => item.id === selectedClassId),
    [classes, selectedClassId],
  )

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const created = await createTeachingClass({
        code: String(data.get('code') ?? '').toUpperCase(),
        name: String(data.get('name') ?? ''),
      })
      form.reset()
      setSelectedClassId(created.id)
      setMessage('班级已创建，学生注册时可以选择该班级。')
      await loadData()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '班级创建失败。')
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(classGroup: TeachingClass) {
    if (!globalThis.confirm(`确定删除班级“${classGroup.name}”吗？历史任务和记录会保留。`)) return
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await deleteTeachingClass(classGroup.id)
      if (selectedClassId === classGroup.id) setSelectedClassId('')
      setMessage('班级已删除，历史任务和记录保持不变。')
      await loadData()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '班级删除失败。')
    } finally {
      setLoading(false)
    }
  }

  async function handleRemoveStudent(studentId: string) {
    if (!selectedClass) return
    if (!globalThis.confirm('确定将该学生移出班级吗？已有任务名单不会改变。')) return
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await removeClassStudent(selectedClass.id, studentId)
      setMessage('学生已移出班级，已有任务名单保持不变。')
      await loadData()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '移出学生失败。')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="teacher-workspace" aria-labelledby="class-management-title">
      <header className="workspace-header">
        <div>
          <h2 id="class-management-title">班级管理</h2>
          <p>创建班级并查看学生名单；学生注册时可自行选择有效班级。</p>
        </div>
      </header>

      <form className="compact-form management-form--single" onSubmit={handleCreate}>
        <h3>新建班级</h3>
        <label>班级编号<input name="code" pattern="[A-Za-z0-9][A-Za-z0-9_-]*" required /></label>
        <label>班级名称<input name="name" required /></label>
        <button className="button" type="submit" disabled={loading}>创建班级</button>
      </form>

      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}
      {loading && classes.length === 0 && <p className="empty-state">正在加载班级…</p>}
      {!loading && classes.length === 0 && <p className="empty-state">目前没有班级。</p>}

      <div className="class-list">
        {classes.map((classGroup) => (
          <article key={classGroup.id}>
            <header className="class-list__header">
              <div>
                <span>{classGroup.code}</span>
                <h3>{classGroup.name}</h3>
                <p>{classGroup.student_count} 名学生</p>
              </div>
              <div className="class-list__actions">
                <button
                  className="button button--secondary"
                  type="button"
                  onClick={() => setSelectedClassId(classGroup.id)}
                >
                  管理学生
                </button>
                <button
                  className="text-button text-button--danger"
                  type="button"
                  disabled={loading}
                  onClick={() => handleDelete(classGroup)}
                >
                  删除班级
                </button>
              </div>
            </header>
          </article>
        ))}
      </div>

      {selectedClass && (
        <section className="roster-card">
          <div>
            <h3>{selectedClass.name}学生名单</h3>
            <p>{selectedClass.code} · 共 {selectedClass.student_count} 人</p>
          </div>
          {selectedClass.students.length === 0 ? <p className="empty-state">班级中还没有学生。</p> : (
            <div className="roster-list">
              {selectedClass.students.map((student) => (
                <article key={student.id}>
                  <div><strong>{student.display_name}</strong><span>{student.email}</span></div>
                  <button
                    className="text-button text-button--danger"
                    type="button"
                    disabled={loading}
                    onClick={() => handleRemoveStudent(student.id)}
                  >
                    移出班级
                  </button>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </section>
  )
}
