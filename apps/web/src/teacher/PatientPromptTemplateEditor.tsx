import { FormEvent, useEffect, useState } from 'react'

import {
  ApiError,
  PatientPromptTemplate,
  PatientQuestionItem,
  PatientQuestionTemplate,
  getPatientPromptTemplate,
  getPatientQuestionTemplate,
  savePatientPromptTemplate,
  savePatientQuestionTemplate,
} from '../api/client'

function newQuestion(): PatientQuestionItem {
  return {
    id: `question_${globalThis.crypto.randomUUID().replaceAll('-', '')}`,
    base_question: '',
    answer_criteria: '',
    enabled: true,
  }
}

export function PatientPromptTemplateEditor({ isAdministrator = false }: { isAdministrator?: boolean }) {
  const [template, setTemplate] = useState<PatientPromptTemplate | null>(null)
  const [questionTemplate, setQuestionTemplate] = useState<PatientQuestionTemplate | null>(null)
  const [content, setContent] = useState('')
  const [questions, setQuestions] = useState<PatientQuestionItem[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    Promise.allSettled([getPatientPromptTemplate(), getPatientQuestionTemplate()])
      .then(([promptResult, questionResult]) => {
        if (promptResult.status === 'fulfilled') {
          setTemplate(promptResult.value)
          setContent(promptResult.value.content)
        }
        if (questionResult.status === 'fulfilled') {
          setQuestionTemplate(questionResult.value)
          setQuestions(questionResult.value.questions)
        }
        if (promptResult.status === 'rejected' || questionResult.status === 'rejected') {
          const requestError = promptResult.status === 'rejected'
            ? promptResult.reason
            : questionResult.status === 'rejected'
              ? questionResult.reason
              : null
          setError(requestError instanceof ApiError ? requestError.message : '系统设置加载不完整。')
        }
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

  async function handleQuestionSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!isAdministrator) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const updated = await savePatientQuestionTemplate(questions)
      setQuestionTemplate(updated)
      setQuestions(updated.questions)
      setMessage('默认主动问题已保存。')
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '默认主动问题保存失败。')
    } finally {
      setSaving(false)
    }
  }

  function updateQuestion(index: number, patch: Partial<PatientQuestionItem>) {
    setQuestions((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...patch } : item
    )))
    setMessage('')
  }

  function moveQuestion(index: number, direction: -1 | 1) {
    setQuestions((current) => {
      const target = index + direction
      if (target < 0 || target >= current.length) return current
      const updated = [...current]
      ;[updated[index], updated[target]] = [updated[target], updated[index]]
      return updated
    })
    setMessage('')
  }

  return (
    <section className="teacher-workspace" aria-labelledby="system-settings-title">
      <header className="workspace-header">
        <div>
          <h2 id="system-settings-title">系统设置</h2>
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


      {questionTemplate && (
        <form className="editor-card prompt-template-form" onSubmit={handleQuestionSubmit}>
          <h3>{questionTemplate.name}</h3>
          <p className="section-help">
            病例草稿默认使用这里的列表，发布后会保存快照。主动问题只判断是否得到实质回应，不判断医学结论是否正确。
          </p>
          <div className="repeat-list">
            {questions.map((item, index) => (
              <article className="repeat-item" key={item.id}>
                <div className="repeat-item__header">
                  <strong>主动问题 {index + 1}</strong>
                  {isAdministrator && (
                    <div>
                      <button type="button" className="text-button" disabled={index === 0} onClick={() => moveQuestion(index, -1)}>上移</button>
                      <button type="button" className="text-button" disabled={index === questions.length - 1} onClick={() => moveQuestion(index, 1)}>下移</button>
                      <button type="button" className="text-button" disabled={questions.length <= 1} onClick={() => setQuestions((current) => current.filter((_, itemIndex) => itemIndex !== index))}>删除</button>
                    </div>
                  )}
                </div>
                <div className="form-grid">
                  <label className="form-grid__wide">
                    基础问法
                    <input
                      value={item.base_question}
                      maxLength={300}
                      readOnly={!isAdministrator}
                      onChange={(event) => updateQuestion(index, { base_question: event.target.value })}
                      required
                    />
                  </label>
                  <label className="form-grid__wide">
                    实质回应判定要点
                    <textarea
                      value={item.answer_criteria}
                      maxLength={1000}
                      rows={3}
                      readOnly={!isAdministrator}
                      onChange={(event) => updateQuestion(index, { answer_criteria: event.target.value })}
                      required
                    />
                  </label>
                  <label className="checkbox-field">
                    <input
                      type="checkbox"
                      checked={item.enabled}
                      disabled={!isAdministrator}
                      onChange={(event) => updateQuestion(index, { enabled: event.target.checked })}
                    />
                    启用这个问题
                  </label>
                </div>
              </article>
            ))}
          </div>
          {isAdministrator ? (
            <div className="prompt-template-actions">
              <button className="button button--secondary" type="button" disabled={questions.length >= 20} onClick={() => setQuestions((current) => [...current, newQuestion()])}>
                添加主动问题
              </button>
              <button className="button" type="submit" disabled={saving || !questions.some((item) => item.enabled) || questions.some((item) => !item.base_question.trim() || !item.answer_criteria.trim())}>
                {saving ? '正在保存…' : '保存默认主动问题'}
              </button>
              {questionTemplate.updated_by_name && <span>最近由 {questionTemplate.updated_by_name} 更新</span>}
            </div>
          ) : (
            <small>只有管理员可以修改全局主动问题；你可以在病例中使用自定义列表。</small>
          )}
        </form>
      )}
    </section>
  )
}
