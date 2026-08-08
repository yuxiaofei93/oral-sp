import { FormEvent, useEffect, useMemo, useState } from 'react'

import {
  ApiError,
  ManagedStudent,
  ManagedStudentFilters,
  TeachingClass,
  getManagedStudent,
  listManagedStudents,
  listTeachingClasses,
  updateManagedStudentClass,
} from '../api/client'

function classSummary(student: ManagedStudent) {
  if (student.classes.length === 0) return '未分班'
  return student.classes.map((item) => (
    `${item.name}${item.is_active ? '' : '（已删除）'}`
  )).join('、')
}

function joinedDate(value: string) {
  return new Date(value).toLocaleDateString('zh-CN')
}

export function StudentManagement() {
  const [students, setStudents] = useState<ManagedStudent[]>([])
  const [classes, setClasses] = useState<TeachingClass[]>([])
  const [nameFilter, setNameFilter] = useState('')
  const [emailFilter, setEmailFilter] = useState('')
  const [classFilter, setClassFilter] = useState('')
  const [selectedStudent, setSelectedStudent] = useState<ManagedStudent | null>(null)
  const [editingClass, setEditingClass] = useState(false)
  const [targetClassId, setTargetClassId] = useState('')
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const activeClasses = useMemo(
    () => classes.filter((item) => item.is_active),
    [classes],
  )

  async function loadData(filters: ManagedStudentFilters = {}) {
    setLoading(true)
    setError('')
    try {
      const [nextStudents, nextClasses] = await Promise.all([
        listManagedStudents(filters),
        listTeachingClasses(),
      ])
      setStudents(nextStudents)
      setClasses(nextClasses)
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '学员列表加载失败。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  function handleFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSelectedStudent(null)
    setEditingClass(false)
    setMessage('')
    void loadData({
      name: nameFilter.trim(),
      email: emailFilter.trim(),
      class_group_id: classFilter,
    })
  }

  function clearFilters() {
    setNameFilter('')
    setEmailFilter('')
    setClassFilter('')
    setSelectedStudent(null)
    setEditingClass(false)
    setMessage('')
    void loadData()
  }

  async function openStudent(studentId: string) {
    setDetailLoading(true)
    setError('')
    setMessage('')
    setEditingClass(false)
    try {
      setSelectedStudent(await getManagedStudent(studentId))
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '学员信息加载失败。')
    } finally {
      setDetailLoading(false)
    }
  }

  function startClassChange() {
    if (!selectedStudent) return
    const currentClass = selectedStudent.classes.find((item) => item.is_active)
    setTargetClassId(currentClass?.id ?? activeClasses[0]?.id ?? '')
    setEditingClass(true)
    setError('')
    setMessage('')
  }

  async function saveClassChange() {
    if (!selectedStudent || !targetClassId) return
    const targetClass = activeClasses.find((item) => item.id === targetClassId)
    if (!targetClass) return
    if (!globalThis.confirm(
      `确定将“${selectedStudent.display_name}”调整到“${targetClass.name}”吗？已有考试任务名单不会改变。`,
    )) return

    setLoading(true)
    setError('')
    setMessage('')
    try {
      const updated = await updateManagedStudentClass(selectedStudent.id, targetClassId)
      setSelectedStudent(updated)
      setStudents((items) => items.map((item) => item.id === updated.id ? updated : item))
      setEditingClass(false)
      setMessage(`已将${updated.display_name}调整到“${targetClass.name}”。`)
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '班级调整失败。')
    } finally {
      setLoading(false)
    }
  }

  const classUnchanged = selectedStudent?.classes.length === 1
    && selectedStudent.classes[0].id === targetClassId

  return (
    <section className="teacher-workspace" aria-labelledby="student-management-title">
      <header className="workspace-header">
        <div>
          <h2 id="student-management-title">学员管理</h2>
        </div>
      </header>

      <form className="student-filters" aria-label="筛选学员" onSubmit={handleFilter}>
        <label>
          姓名
          <input
            value={nameFilter}
            onChange={(event) => setNameFilter(event.target.value)}
            placeholder="输入学员姓名"
          />
        </label>
        <label>
          邮箱
          <input
            type="search"
            value={emailFilter}
            onChange={(event) => setEmailFilter(event.target.value)}
            placeholder="输入邮箱"
          />
        </label>
        <label>
          班级
          <select value={classFilter} onChange={(event) => setClassFilter(event.target.value)}>
            <option value="">全部班级</option>
            {classes.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <div className="student-filters__actions">
          <button className="button" type="submit" disabled={loading}>筛选</button>
          <button className="button button--secondary" type="button" disabled={loading} onClick={clearFilters}>
            重置
          </button>
        </div>
      </form>

      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}
      {loading && students.length === 0 && <p className="empty-state">正在加载学员…</p>}
      {!loading && students.length === 0 && <p className="empty-state">没有符合条件的学员。</p>}

      {students.length > 0 && (
        <div className="student-table-wrap">
          <table className="student-table">
            <thead>
              <tr>
                <th>姓名</th>
                <th>邮箱</th>
                <th>班级</th>
                <th>注册时间</th>
                <th>状态</th>
                <th><span className="visually-hidden">操作</span></th>
              </tr>
            </thead>
            <tbody>
              {students.map((student) => (
                <tr key={student.id}>
                  <td><strong>{student.display_name}</strong></td>
                  <td>{student.email}</td>
                  <td>{classSummary(student)}</td>
                  <td>{joinedDate(student.date_joined)}</td>
                  <td>
                    <span className={`student-status ${student.is_active ? '' : 'student-status--inactive'}`}>
                      {student.is_active ? '正常' : '已停用'}
                    </span>
                  </td>
                  <td>
                    <button
                      className="text-button"
                      type="button"
                      disabled={detailLoading}
                      onClick={() => openStudent(student.id)}
                    >
                      查看详情
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedStudent && (
        <section className="student-detail" aria-labelledby="student-detail-title">
          <header>
            <div>
              <span>学员基本信息</span>
              <h3 id="student-detail-title">{selectedStudent.display_name}</h3>
            </div>
            <button
              className="text-button"
              type="button"
              onClick={() => {
                setSelectedStudent(null)
                setEditingClass(false)
              }}
            >
              关闭
            </button>
          </header>
          <dl className="student-detail__facts">
            <div><dt>邮箱</dt><dd>{selectedStudent.email}</dd></div>
            <div><dt>当前班级</dt><dd>{classSummary(selectedStudent)}</dd></div>
            <div><dt>注册时间</dt><dd>{joinedDate(selectedStudent.date_joined)}</dd></div>
            <div><dt>账号状态</dt><dd>{selectedStudent.is_active ? '正常' : '已停用'}</dd></div>
          </dl>

          {editingClass ? (
            <div className="student-detail__class-editor">
              <label>
                调整到
                <select
                  aria-label="调整到班级"
                  value={targetClassId}
                  onChange={(event) => setTargetClassId(event.target.value)}
                  disabled={loading}
                >
                  {activeClasses.map((item) => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
              </label>
              <button
                className="button"
                type="button"
                disabled={loading || !targetClassId || classUnchanged}
                onClick={saveClassChange}
              >
                保存调整
              </button>
              <button
                className="button button--secondary"
                type="button"
                disabled={loading}
                onClick={() => setEditingClass(false)}
              >
                取消
              </button>
            </div>
          ) : (
            <button
              className="button button--secondary"
              type="button"
              disabled={activeClasses.length === 0}
              title={activeClasses.length === 0 ? '没有可转入的有效班级' : undefined}
              onClick={startClassChange}
            >
              调整班级
            </button>
          )}
        </section>
      )}
    </section>
  )
}
