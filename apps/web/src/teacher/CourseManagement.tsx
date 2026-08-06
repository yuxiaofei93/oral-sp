import { FormEvent, useEffect, useState } from 'react'

import {
  ApiError,
  TeachingCourse,
  createTeachingCourse,
  deleteTeachingCourse,
  listTeachingCourses,
} from '../api/client'

export function CourseManagement() {
  const [courses, setCourses] = useState<TeachingCourse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function loadCourses() {
    setLoading(true)
    setError('')
    try {
      setCourses(await listTeachingCourses())
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '课程列表加载失败。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadCourses()
  }, [])

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await createTeachingCourse({
        code: String(data.get('code') ?? '').toUpperCase(),
        name: String(data.get('name') ?? ''),
      })
      form.reset()
      setMessage('课程已创建。')
      await loadCourses()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '课程创建失败。')
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(course: TeachingCourse) {
    if (!globalThis.confirm(`确定删除课程“${course.name}”吗？历史任务和记录会保留。`)) return
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await deleteTeachingCourse(course.id)
      setMessage('课程已删除，历史任务和记录保持不变。')
      await loadCourses()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '课程删除失败。')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="teacher-workspace" aria-labelledby="course-management-title">
      <header className="workspace-header">
        <div>
          <h2 id="course-management-title">课程管理</h2>
          <p>创建课程并维护课程列表。删除课程不会清除已经发布的任务和历史记录。</p>
        </div>
      </header>

      <form className="compact-form management-form--single" onSubmit={handleCreate}>
        <h3>新建课程</h3>
        <label>课程编号<input name="code" pattern="[A-Za-z0-9][A-Za-z0-9_-]*" required /></label>
        <label>课程名称<input name="name" required /></label>
        <button className="button" type="submit" disabled={loading}>创建课程</button>
      </form>

      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}
      {loading && courses.length === 0 && <p className="empty-state">正在加载课程…</p>}
      {!loading && courses.length === 0 && <p className="empty-state">目前没有课程。</p>}

      <div className="course-list">
        {courses.map((course) => (
          <article key={course.id}>
            <header className="course-list__header">
              <div>
                <span>{course.code}</span>
                <h3>{course.name}</h3>
                <p>{course.class_count} 个班级</p>
              </div>
              <button
                className="text-button text-button--danger"
                type="button"
                disabled={loading}
                onClick={() => handleDelete(course)}
              >
                删除课程
              </button>
            </header>
          </article>
        ))}
      </div>
    </section>
  )
}
