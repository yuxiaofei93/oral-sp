import { useEffect, useState } from 'react'

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

  async function handleCreate() {
    setLoading(true)
    setError('')
    try {
      const nextDraft = await createTeacherCase()
      setDraft(nextDraft)
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
        <button className="button" type="button" disabled={loading} onClick={() => void handleCreate()}>
          新建病例
        </button>
      </header>

      {error && <p className="form-error">{error}</p>}
      {loading && <p className="empty-state">正在加载病例…</p>}
      {!loading && cases.length === 0 && <p className="empty-state">还没有病例。创建第一个文字教学病例吧。</p>}

      <div className="case-list">
        {cases.map((item) => (
          <article key={item.id}>
            <div>
              <span>{item.code}</span>
              <h3>{item.draft?.title_internal ?? '无草稿'}</h3>
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
