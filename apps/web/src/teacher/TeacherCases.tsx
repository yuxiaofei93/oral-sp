import { FormEvent, useEffect, useState } from 'react'

import {
  ApiError,
  CaseDraft,
  CaseSummary,
  createTeacherCase,
  getCaseDraft,
  listTeacherCases,
} from '../api/client'
import { CaseEditor } from './CaseEditor'

export function TeacherCases() {
  const [cases, setCases] = useState<CaseSummary[]>([])
  const [draft, setDraft] = useState<CaseDraft | null>(null)
  const [creating, setCreating] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function loadCases() {
    setLoading(true)
    setError('')
    try {
      setCases(await listTeacherCases())
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '病例列表加载失败。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadCases()
  }, [])

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoading(true)
    setError('')
    const data = new FormData(event.currentTarget)
    try {
      const nextDraft = await createTeacherCase({
        code: String(data.get('code') ?? '').toUpperCase(),
        title_internal: String(data.get('title_internal') ?? ''),
        title_student: String(data.get('title_student') ?? ''),
      })
      setDraft(nextDraft)
      setCreating(false)
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '病例创建失败。')
    } finally {
      setLoading(false)
    }
  }

  async function openCase(caseId: string) {
    setLoading(true)
    setError('')
    try {
      setDraft(await getCaseDraft(caseId))
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '病例草稿加载失败。')
    } finally {
      setLoading(false)
    }
  }

  if (draft) {
    return (
      <CaseEditor
        initialDraft={draft}
        onClose={() => {
          setDraft(null)
          void loadCases()
        }}
      />
    )
  }

  return (
    <section className="teacher-workspace" aria-labelledby="teacher-cases-title">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">TEACHER WORKSPACE</p>
          <h2 id="teacher-cases-title">结构化病例</h2>
          <p>用标准表单维护病例事实、检查、诊断和评分规则，不需要编写提示词。</p>
        </div>
        <button className="button" type="button" onClick={() => setCreating((value) => !value)}>
          {creating ? '取消新建' : '新建病例'}
        </button>
      </header>

      {creating && (
        <form className="new-case-form" onSubmit={handleCreate}>
          <label>病例编号<input name="code" placeholder="OM-001" pattern="[A-Za-z0-9][A-Za-z0-9_-]*" required /></label>
          <label>内部名称<input name="title_internal" required /></label>
          <label>学生可见名称<input name="title_student" required /></label>
          <button className="button" type="submit" disabled={loading}>创建并编辑</button>
        </form>
      )}

      {error && <p className="form-error">{error}</p>}
      {loading && <p className="empty-state">正在加载病例…</p>}
      {!loading && cases.length === 0 && <p className="empty-state">还没有病例。创建第一个文字教学病例吧。</p>}

      <div className="case-list">
        {cases.map((item) => (
          <article key={item.id}>
            <div>
              <span>{item.code}</span>
              <h3>{item.draft?.title_internal ?? '无草稿'}</h3>
              <p>{item.draft?.title_student}</p>
            </div>
            <div className="case-list__meta">
              <span>{item.latest_published ? `已发布 v${item.latest_published.version_number}` : '尚未发布'}</span>
              <button className="button button--secondary" type="button" onClick={() => openCase(item.id)}>编辑草稿</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}

