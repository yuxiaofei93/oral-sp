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
        setError(requestError instanceof ApiError ? requestError.message : '默认表达风格加载失败。')
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
      setMessage('默认表达风格已保存。')
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '默认表达风格保存失败。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="teacher-workspace" aria-labelledby="system-settings-title">
      <header className="workspace-header">
        <div>
          <h2 id="system-settings-title">系统设置</h2>
        </div>
      </header>

      {loading && <p className="empty-state">正在加载默认表达风格…</p>}
      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}

      {template && (
        <form className="editor-card prompt-template-form" onSubmit={handleSubmit}>
          <h3>{template.name}</h3>
          <p className="section-help">
            这里只配置患者的语气、情绪、配合程度和回答习惯。事实边界、安全规则和输出格式由系统固定管理，不能在此修改。修改会应用到使用默认风格的草稿；已发布病例保存的是发布当时的表达风格，不会被改变。
          </p>
          <div className="form-grid">
            <label className="form-grid__wide">
              默认患者表达风格
              <textarea
                aria-label="默认患者表达风格"
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
              {saving ? '正在保存…' : '保存默认风格'}
            </button>
            {template.updated_by_name && <span>最近由 {template.updated_by_name} 更新</span>}
          </div>
        </form>
      )}
    </section>
  )
}
