import { FormEvent, useEffect, useMemo, useState } from 'react'

import {
  ApiError,
  TeachingClass,
  TeachingCourse,
  createTeachingClass,
  listTeachingClasses,
  listTeachingCourses,
  removeClassStudent,
} from '../api/client'

export function ClassManagement() {
  const [courses, setCourses] = useState<TeachingCourse[]>([])
  const [classes, setClasses] = useState<TeachingClass[]>([])
  const [selectedClassId, setSelectedClassId] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [nextCourses, nextClasses] = await Promise.all([
        listTeachingCourses(),
        listTeachingClasses(),
      ])
      setCourses(nextCourses)
      setClasses(nextClasses)
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
        course_id: String(data.get('course_id') ?? ''),
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
        <label>所属课程
          <select name="course_id" required disabled={courses.length === 0}>
            <option value="">请选择课程</option>
            {courses.map((course) => (
              <option value={course.id} key={course.id}>{course.code} · {course.name}</option>
            ))}
          </select>
        </label>
        <label>班级编号<input name="code" pattern="[A-Za-z0-9][A-Za-z0-9_-]*" required /></label>
        <label>班级名称<input name="name" required /></label>
        <button className="button" type="submit" disabled={loading || courses.length === 0}>创建班级</button>
      </form>

      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}
      {loading && classes.length === 0 && <p className="empty-state">正在加载班级…</p>}
      {!loading && courses.length === 0 && <p className="empty-state">请先在课程管理中创建课程。</p>}
      {!loading && courses.length > 0 && classes.length === 0 && <p className="empty-state">目前没有班级。</p>}

      <div className="course-list">
        {classes.map((classGroup) => (
          <article key={classGroup.id}>
            <header className="course-list__header">
              <div>
                <span>{classGroup.course_name} · {classGroup.code}</span>
                <h3>{classGroup.name}</h3>
                <p>{classGroup.student_count} 名学生</p>
              </div>
              <button
                className="button button--secondary"
                type="button"
                onClick={() => setSelectedClassId(classGroup.id)}
              >
                管理学生
              </button>
            </header>
          </article>
        ))}
      </div>

      {selectedClass && (
        <section className="roster-card">
          <div>
            <h3>{selectedClass.name}学生名单</h3>
            <p>{selectedClass.course_name} · 共 {selectedClass.student_count} 人</p>
          </div>
          {selectedClass.students.length === 0 ? <p className="empty-state">班级中还没有学生。</p> : (
            <div className="roster-list">
              {selectedClass.students.map((student) => (
                <article key={student.id}>
                  <div><strong>{student.display_name}</strong><span>{student.phone}</span></div>
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
