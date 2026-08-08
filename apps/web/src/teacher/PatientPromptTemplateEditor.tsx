import { FormEvent, useEffect, useState } from 'react'

import {
  ApiError,
  PatientPromptTemplate,
  getPatientPromptTemplate,
  savePatientPromptTemplate,
} from '../api/client'

export function PatientPromptTemplateEditor() {
  const [template, setTemplate] = useState<PatientPromptTemplate | null>(null)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    getPatientPromptTemplate()
      .then((result) => {
        setTemplate(result)
        setContent(result.content)
      })
      .catch((requestError: unknown) => {
        setError(requestError instanceof ApiError ? requestError.message : '默认提示词加载失败。')
      })
      .finally(() => setLoading(false))
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const updated = await savePatientPromptTemplate(content)
      setTemplate(updated)
      setContent(updated.content)
      setMessage('默认提示词已保存。')
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '默认提示词保存失败。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="teacher-workspace" aria-labelledby="patient-prompt-template-title">
      <header className="workspace-header">
        <div>
          <h2 id="patient-prompt-template-title">提示词模板</h2>
        </div>
      </header>

      {loading && <p className="empty-state">正在加载默认提示词…</p>}
      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}

      {template && (
        <form className="editor-card prompt-template-form" onSubmit={handleSubmit}>
          <h3>{template.name}</h3>
          <p className="section-help">
            修改会应用到使用默认模板的草稿；已发布病例保存的是发布当时的提示词，不会被改变。
          </p>
          <div className="form-grid">
            <label className="form-grid__wide">
              默认患者问诊提示词
              <textarea
                aria-label="默认患者问诊提示词"
                rows={16}
                maxLength={8000}
                value={content}
                onChange={(event) => {
                  setContent(event.target.value)
                  setMessage('')
                }}
                required
              />
              <small>{content.length} / 8000 字</small>
            </label>
          </div>
          <div className="prompt-template-actions">
            <button className="button" type="submit" disabled={saving || !content.trim()}>
              {saving ? '正在保存…' : '保存默认模板'}
            </button>
            {template.updated_by_name && <span>最近由 {template.updated_by_name} 更新</span>}
          </div>
        </form>
      )}
    </section>
  )
}
