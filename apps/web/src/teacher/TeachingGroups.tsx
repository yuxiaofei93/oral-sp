import { FormEvent, useEffect, useMemo, useState } from 'react'

import {
  ApiError,
  TeachingCourse,
  addClassStudents,
  createTeachingClass,
  createTeachingCourse,
  listTeachingCourses,
  removeClassStudent,
} from '../api/client'

function rosterError(error: unknown) {
  if (!(error instanceof ApiError)) return '学生名单更新失败。'
  const details = error.details
  if (details && typeof details === 'object') {
    const data = details as { missing?: string[]; not_students?: string[] }
    const parts = []
    if (data.missing?.length) parts.push(`未注册：${data.missing.join('、')}`)
    if (data.not_students?.length) parts.push(`不是学生账号：${data.not_students.join('、')}`)
    if (parts.length) return `${error.message} ${parts.join('；')}`
  }
  return error.message
}

function parsePhones(source: string) {
  return source.split(/[\s,，;；]+/).map((phone) => phone.trim()).filter(Boolean)
}

export function TeachingGroups() {
  const [courses, setCourses] = useState<TeachingCourse[]>([])
  const [selectedClassId, setSelectedClassId] = useState('')
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

  const selectedClass = useMemo(
    () => courses.flatMap((course) => course.classes).find((item) => item.id === selectedClassId),
    [courses, selectedClassId],
  )

  async function handleCourseCreate(event: FormEvent<HTMLFormElement>) {
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

  async function handleClassCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await createTeachingClass({
        course_id: String(data.get('course_id') ?? ''),
        code: String(data.get('code') ?? '').toUpperCase(),
        name: String(data.get('name') ?? ''),
      })
      form.reset()
      setMessage('班级已创建，可以开始添加学生。')
      await loadCourses()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '班级创建失败。')
    } finally {
      setLoading(false)
    }
  }

  async function handleRosterAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedClass) return
    const form = event.currentTarget
    const phones = parsePhones(String(new FormData(form).get('phones') ?? ''))
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const result = await addClassStudents(selectedClass.id, phones)
      form.reset()
      setMessage(`已新增 ${result.created_count} 人，${result.existing_count} 人原本已在班级中。`)
      await loadCourses()
    } catch (requestError: unknown) {
      setError(rosterError(requestError))
    } finally {
      setLoading(false)
    }
  }

  async function handleRemoveStudent(studentId: string) {
    if (!selectedClass) return
    if (!globalThis.confirm('确定移出该学生吗？只影响以后发布的任务，已有任务名单不会改变。')) return
    setLoading(true)
    setError('')
    try {
      await removeClassStudent(selectedClass.id, studentId)
      setMessage('学生已移出班级，已有任务名单保持不变。')
      await loadCourses()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '移出学生失败。')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="teacher-workspace" aria-labelledby="teaching-groups-title">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">TEACHING GROUPS</p>
          <h2 id="teaching-groups-title">课程、班级与学生</h2>
          <p>学生需先自行注册，再由教师通过手机号加入班级。</p>
        </div>
      </header>

      <div className="management-forms">
        <form className="compact-form" onSubmit={handleCourseCreate}>
          <h3>新建课程</h3>
          <label>课程编号<input name="code" placeholder="ORAL-2026" pattern="[A-Za-z0-9][A-Za-z0-9_-]*" required /></label>
          <label>课程名称<input name="name" placeholder="口腔问诊训练" required /></label>
          <button className="button" type="submit" disabled={loading}>创建课程</button>
        </form>

        <form className="compact-form" onSubmit={handleClassCreate}>
          <h3>新建班级</h3>
          <label>所属课程
            <select name="course_id" required disabled={courses.length === 0}>
              <option value="">请选择课程</option>
              {courses.map((course) => <option value={course.id} key={course.id}>{course.code} · {course.name}</option>)}
            </select>
          </label>
          <label>班级编号<input name="code" placeholder="CLASS-A" pattern="[A-Za-z0-9][A-Za-z0-9_-]*" required /></label>
          <label>班级名称<input name="name" placeholder="2026 级 A 班" required /></label>
          <button className="button" type="submit" disabled={loading || courses.length === 0}>创建班级</button>
        </form>
      </div>

      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}
      {loading && courses.length === 0 && <p className="empty-state">正在加载课程…</p>}
      {!loading && courses.length === 0 && <p className="empty-state">目前没有课程，请先创建一门课程。</p>}

      <div className="course-list">
        {courses.map((course) => (
          <article key={course.id}>
            <header><span>{course.code}</span><h3>{course.name}</h3></header>
            {course.classes.length === 0 ? <p>还没有班级。</p> : (
              <div className="class-chips">
                {course.classes.map((classGroup) => (
                  <button
                    className={selectedClassId === classGroup.id ? 'is-active' : ''}
                    type="button"
                    key={classGroup.id}
                    onClick={() => setSelectedClassId(classGroup.id)}
                  >
                    {classGroup.name}<span>{classGroup.student_count} 人</span>
                  </button>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>

      {selectedClass && (
        <section className="roster-card">
          <div>
            <h3>{selectedClass.name}学生名单</h3>
            <p>支持每行一个手机号，也可以使用空格或逗号分隔；每次最多 100 个。</p>
          </div>
          <form onSubmit={handleRosterAdd}>
            <textarea name="phones" rows={4} placeholder={'13800138000\n13900139000'} required />
            <button className="button" type="submit" disabled={loading}>批量加入学生</button>
          </form>
          {selectedClass.students.length === 0 ? <p className="empty-state">班级中还没有学生。</p> : (
            <div className="roster-list">
              {selectedClass.students.map((student) => (
                <article key={student.id}>
                  <div><strong>{student.display_name}</strong><span>{student.phone}</span></div>
                  <button className="text-button text-button--danger" type="button" onClick={() => handleRemoveStudent(student.id)}>移出班级</button>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </section>
  )
}
