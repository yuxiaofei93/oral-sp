import { FormEvent, useEffect, useState } from 'react'

import {
  ApiError,
  PatientFollowUpTemplate,
  PatientPromptTemplate,
  getPatientFollowUpTemplate,
  getPatientPromptTemplate,
  savePatientFollowUpTemplate,
  savePatientPromptTemplate,
} from '../api/client'

function moveItem(items: string[], index: number, offset: number): string[] {
  const target = index + offset
  if (target < 0 || target >= items.length) return items
  const updated = [...items]
  ;[updated[index], updated[target]] = [updated[target], updated[index]]
  return updated
}

export function PatientPromptTemplateEditor() {
  const [template, setTemplate] = useState<PatientPromptTemplate | null>(null)
  const [content, setContent] = useState('')
  const [followUpTemplate, setFollowUpTemplate] = useState<PatientFollowUpTemplate | null>(null)
  const [questions, setQuestions] = useState<string[]>([])
  const [closingText, setClosingText] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [followUpSaving, setFollowUpSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [followUpMessage, setFollowUpMessage] = useState('')

  useEffect(() => {
    Promise.all([getPatientPromptTemplate(), getPatientFollowUpTemplate()])
      .then(([styleResult, followUpResult]) => {
        setTemplate(styleResult)
        setContent(styleResult.content)
        setFollowUpTemplate(followUpResult)
        setQuestions(followUpResult.questions)
        setClosingText(followUpResult.closing_text)
      })
      .catch((requestError: unknown) => {
        setError(requestError instanceof ApiError ? requestError.message : '系统设置加载失败。')
      })
      .finally(() => setLoading(false))
  }, [])

  async function handleStyleSubmit(event: FormEvent<HTMLFormElement>) {
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

  async function handleFollowUpSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFollowUpSaving(true)
    setError('')
    setFollowUpMessage('')
    try {
      const updated = await savePatientFollowUpTemplate(
        questions.map((question) => question.trim()),
        closingText.trim(),
      )
      setFollowUpTemplate(updated)
      setQuestions(updated.questions)
      setClosingText(updated.closing_text)
      setFollowUpMessage('默认患者主动问答已保存。')
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '默认患者主动问答保存失败。')
    } finally {
      setFollowUpSaving(false)
    }
  }

  return (
    <section className="teacher-workspace" aria-labelledby="system-settings-title">
      <header className="workspace-header">
        <div><h2 id="system-settings-title">系统设置</h2></div>
      </header>

      {loading && <p className="empty-state">正在加载系统设置…</p>}
      {error && <p className="form-error">{error}</p>}

      {template && (
        <form className="editor-card prompt-template-form" onSubmit={handleStyleSubmit}>
          <h3>{template.name}</h3>
          <p className="section-help">
            这里只配置患者的语气、情绪、配合程度和回答习惯。事实边界、安全规则和输出格式由系统固定管理，不能在此修改。修改会应用到使用默认风格的草稿；已发布病例保存的是发布当时的表达风格，不会被改变。
          </p>
          {message && <p className="form-success">{message}</p>}
          <div className="form-grid">
            <label className="form-grid__wide">
              默认患者表达风格
              <textarea
                aria-label="默认患者表达风格"
                rows={10}
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

      {followUpTemplate && (
        <form className="editor-card prompt-template-form" onSubmit={handleFollowUpSubmit}>
          <h3>{followUpTemplate.name}</h3>
          <p className="section-help">
            首次完成口腔体格检查后，患者会按顺序一次询问一个问题；学生每回答一次，患者再询问下一项。病例可以跟随此默认设置、自定义或关闭。
          </p>
          {followUpMessage && <p className="form-success">{followUpMessage}</p>}
          <div className="repeat-list">
            {questions.map((question, index) => (
              <article className="repeat-item" key={`follow-up-${index}`}>
                <div className="repeat-item__header">
                  <strong>主动询问 {index + 1}</strong>
                  <div>
                    <button type="button" disabled={index === 0} onClick={() => setQuestions(moveItem(questions, index, -1))}>上移</button>
                    <button type="button" disabled={index === questions.length - 1} onClick={() => setQuestions(moveItem(questions, index, 1))}>下移</button>
                    <button type="button" disabled={questions.length === 1} onClick={() => setQuestions(questions.filter((_, itemIndex) => itemIndex !== index))}>删除</button>
                  </div>
                </div>
                <label>
                  <span className="visually-hidden">主动询问 {index + 1}</span>
                  <input
                    aria-label={`主动询问 ${index + 1}`}
                    maxLength={500}
                    value={question}
                    onChange={(event) => setQuestions(questions.map((item, itemIndex) => (
                      itemIndex === index ? event.target.value : item
                    )))}
                    required
                  />
                </label>
              </article>
            ))}
          </div>
          <button className="button button--secondary" type="button" onClick={() => setQuestions([...questions, ''])}>
            添加主动询问
          </button>
          <div className="form-grid">
            <label className="form-grid__wide">
              最后一项回答后的收尾语
              <input
                aria-label="默认主动问答收尾语"
                maxLength={500}
                value={closingText}
                onChange={(event) => setClosingText(event.target.value)}
                required
              />
            </label>
          </div>
          <div className="prompt-template-actions">
            <button
              className="button"
              type="submit"
              disabled={followUpSaving || questions.some((question) => !question.trim()) || !closingText.trim()}
            >
              {followUpSaving ? '正在保存…' : '保存默认主动问答'}
            </button>
            {followUpTemplate.updated_by_name && <span>最近由 {followUpTemplate.updated_by_name} 更新</span>}
          </div>
        </form>
      )}
    </section>
  )
}
