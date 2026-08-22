import { ChangeEvent, ReactNode, useEffect, useRef, useState } from 'react'

import {
  ApiError,
  CaseDraft,
  CaseFact,
  CaseTest,
  deletePhysicalExamAsset,
  DiagnosisRule,
  publishCase,
  saveCaseDraft,
  ScoringItem,
  uploadPhysicalExamAsset,
} from '../api/client'

const editorSections = [
  { id: 'basic-info', label: '基础信息' },
  { id: 'patient-prompt', label: '患者表达风格' },
  { id: 'patient-facts', label: '病情信息' },
  { id: 'physical-exam', label: '口腔体格检查' },
  { id: 'case-tests', label: '辅助检查资料' },
  { id: 'diagnosis-rules', label: '诊断规则' },
  { id: 'scoring-rules', label: '评分规则' },
]

const AUTO_SAVE_DELAY_MS = 500

type SaveStatus = 'saved' | 'dirty' | 'saving' | 'error'

const emptyFact = (facts: CaseFact[]): CaseFact => {
  const nextCodeNumber = facts.reduce((maximum, fact) => {
    const match = /^fact\.(\d+)$/.exec(fact.code)
    return match ? Math.max(maximum, Number(match[1])) : maximum
  }, 0) + 1
  const nextDisplayOrder = facts.reduce(
    (maximum, fact) => Math.max(maximum, fact.display_order),
    -1,
  ) + 1

  return {
    code: `fact.${nextCodeNumber}`,
    standard_fact: '',
    patient_expression: '',
    disclosure_mode: 'on_question',
    certainty: 'certain',
    teacher_notes: '',
    display_order: nextDisplayOrder,
  }
}

const emptyTest = (order: number): CaseTest => ({
  code: `test.${order + 1}`,
  name: '',
  category: '',
  student_description: '',
  result_text: '',
  teacher_interpretation: '',
  release_stage: 'test_results',
  requires_request: true,
  prerequisite_code: '',
  display_order: order,
})

const emptyDiagnosis = (order: number): DiagnosisRule => ({
  diagnosis_type: 'differential',
  name: '',
  aliases: [],
  supporting_evidence: [],
  opposing_evidence: [],
  is_required: true,
  display_order: order,
})

const emptyScoringItem = (order: number): ScoringItem => ({
  code: `score.${order + 1}`,
  dimension: 'history',
  label: '',
  description: '',
  max_score: '1.00',
  evaluation_method: 'rule',
  matching_config: { source: 'history_facts', fact_codes: [] },
  student_feedback: '',
  teacher_notes: '',
  is_student_visible: true,
  display_order: order,
})

function commaList(value: string): string[] {
  return value
    .split(/[,，、;；\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function DelimitedListInput({
  value,
  onChange,
}: {
  value: string[]
  onChange: (value: string[]) => void
}) {
  const [text, setText] = useState(value.join('，'))

  useEffect(() => {
    setText(value.join('，'))
  }, [value])

  return (
    <input
      value={text}
      onChange={(event) => setText(event.target.value)}
      onBlur={() => {
        const normalized = commaList(text)
        setText(normalized.join('，'))
        onChange(normalized)
      }}
    />
  )
}

function EditorCard({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="editor-card" id={id}>
      <h3>{title}</h3>
      {children}
    </section>
  )
}

type Props = {
  initialDraft: CaseDraft
  onClose: () => void
}

export function CaseEditor({ initialDraft, onClose }: Props) {
  const [draft, setDraft] = useState(initialDraft)
  const [revision, setRevision] = useState(0)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('saved')
  const [publishing, setPublishing] = useState(false)
  const [mediaBusy, setMediaBusy] = useState(false)
  const [mediaConfirmed, setMediaConfirmed] = useState(false)
  const [error, setError] = useState('')
  const draftRef = useRef(initialDraft)
  const revisionRef = useRef(0)
  const savedRevisionRef = useRef(0)
  const serverUpdatedAtRef = useRef(initialDraft.updated_at)
  const saveInFlightRef = useRef<Promise<boolean> | null>(null)
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function updateDraft(updater: (current: CaseDraft) => CaseDraft) {
    const updated = updater(draftRef.current)
    const nextRevision = revisionRef.current + 1
    draftRef.current = updated
    revisionRef.current = nextRevision
    setDraft(updated)
    setRevision(nextRevision)
    setSaveStatus('dirty')
    setError('')
  }

  function setField<K extends keyof CaseDraft>(field: K, value: CaseDraft[K]) {
    updateDraft((current) => ({ ...current, [field]: value }))
  }

  function setProfile(field: keyof CaseDraft['patient_profile'], value: string | number | null) {
    updateDraft((current) => ({
      ...current,
      patient_profile: { ...current.patient_profile, [field]: value },
    }))
  }

  function setPhysicalExam(
    field: 'findings_text' | 'consent_text',
    value: string,
  ) {
    updateDraft((current) => ({
      ...current,
      physical_exam: { ...current.physical_exam, [field]: value },
    }))
  }

  function setPatientPromptMode(mode: CaseDraft['patient_prompt_mode']) {
    updateDraft((current) => ({
      ...current,
      patient_prompt_mode: mode,
      patient_prompt: mode === 'custom' ? current.default_patient_prompt : '',
      effective_patient_prompt: current.default_patient_prompt,
    }))
  }

  function setPatientPrompt(value: string) {
    updateDraft((current) => ({
      ...current,
      patient_prompt: value,
      effective_patient_prompt: value,
    }))
  }

  function draftPayload(source: CaseDraft): Partial<CaseDraft> {
    return {
      title_internal: source.title_internal,
      difficulty: source.difficulty,
      is_exam_mode: source.is_exam_mode,
      time_limit_minutes: source.time_limit_minutes,
      enabled_stages: source.enabled_stages,
      patient_prompt_mode: source.patient_prompt_mode,
      patient_prompt: source.patient_prompt,
      patient_profile: source.patient_profile,
      physical_exam: source.physical_exam,
      facts: source.facts.map((fact) => ({
        ...fact,
        patient_expression: fact.standard_fact,
      })),
      tests: source.tests,
      diagnosis_rules: source.diagnosis_rules,
      scoring_items: source.scoring_items,
    }
  }

  async function persistLatestDraft(): Promise<boolean> {
    if (saveInFlightRef.current) {
      const inFlight = saveInFlightRef.current
      const result = await inFlight
      if (savedRevisionRef.current < revisionRef.current) return persistLatestDraft()
      return result
    }
    if (savedRevisionRef.current >= revisionRef.current) return true

    const operation = (async () => {
      setError('')
      while (savedRevisionRef.current < revisionRef.current) {
        setSaveStatus('saving')
        const snapshot = draftRef.current
        const snapshotRevision = revisionRef.current
        try {
          const updated = await saveCaseDraft(snapshot.case_id, {
            ...draftPayload(snapshot),
            expected_updated_at: serverUpdatedAtRef.current,
          })
          serverUpdatedAtRef.current = updated.updated_at
          savedRevisionRef.current = snapshotRevision
          const current = { ...draftRef.current, updated_at: updated.updated_at }
          draftRef.current = current
          setDraft(current)
        } catch (requestError: unknown) {
          setSaveStatus('error')
          setError(requestError instanceof ApiError ? requestError.message : '自动保存失败，请稍后重试。')
          return false
        }
      }
      setSaveStatus('saved')
      return true
    })()

    saveInFlightRef.current = operation
    try {
      return await operation
    } finally {
      if (saveInFlightRef.current === operation) saveInFlightRef.current = null
    }
  }

  useEffect(() => {
    if (mediaBusy || revision === 0 || savedRevisionRef.current >= revision) return undefined
    const timer = setTimeout(() => {
      autoSaveTimerRef.current = null
      void persistLatestDraft()
    }, AUTO_SAVE_DELAY_MS)
    autoSaveTimerRef.current = timer
    return () => {
      clearTimeout(timer)
      if (autoSaveTimerRef.current === timer) autoSaveTimerRef.current = null
    }
  }, [mediaBusy, revision])

  function clearAutoSaveTimer() {
    if (!autoSaveTimerRef.current) return
    clearTimeout(autoSaveTimerRef.current)
    autoSaveTimerRef.current = null
  }

  async function handleClose() {
    clearAutoSaveTimer()
    if (await persistLatestDraft()) onClose()
  }

  async function handlePublish() {
    clearAutoSaveTimer()
    setPublishing(true)
    setError('')
    if (!(await persistLatestDraft())) {
      setPublishing(false)
      return
    }
    try {
      await publishCase(draftRef.current.case_id)
      onClose()
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '发布失败，请稍后重试。')
    } finally {
      setPublishing(false)
    }
  }

  function mergeServerMedia(updated: CaseDraft) {
    serverUpdatedAtRef.current = updated.updated_at
    const current = {
      ...draftRef.current,
      updated_at: updated.updated_at,
      physical_exam: {
        ...draftRef.current.physical_exam,
        images: updated.physical_exam.images,
        attachments: updated.physical_exam.attachments,
      },
    }
    draftRef.current = current
    setDraft(current)
    if (savedRevisionRef.current >= revisionRef.current) setSaveStatus('saved')
  }

  async function handleAssetUpload(
    event: ChangeEvent<HTMLInputElement>,
    kind: 'image' | 'attachment',
  ) {
    const input = event.currentTarget
    const files = Array.from(input.files ?? [])
    input.value = ''
    if (files.length === 0) return
    if (!mediaConfirmed) {
      setError('上传前请确认资料已获授权并完成脱敏。')
      return
    }
    clearAutoSaveTimer()
    if (!(await persistLatestDraft())) return
    setMediaBusy(true)
    setError('')
    try {
      for (const file of files) {
        const updated = await uploadPhysicalExamAsset(draftRef.current.case_id, {
          file,
          kind,
          deidentified_confirmed: true,
          expected_updated_at: serverUpdatedAtRef.current,
        })
        mergeServerMedia(updated)
      }
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '文件上传失败。')
    } finally {
      setMediaBusy(false)
    }
  }

  async function handleAssetDelete(assetId: number) {
    clearAutoSaveTimer()
    if (!(await persistLatestDraft())) return
    setMediaBusy(true)
    setError('')
    try {
      const updated = await deletePhysicalExamAsset(
        draftRef.current.case_id,
        assetId,
        serverUpdatedAtRef.current,
      )
      mergeServerMedia(updated)
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '文件删除失败。')
    } finally {
      setMediaBusy(false)
    }
  }

  const saveStateText = publishing
    ? '正在发布…'
    : saveStatus === 'saving'
      ? '正在自动保存…'
      : saveStatus === 'dirty'
        ? '修改将在片刻后自动保存'
        : saveStatus === 'error'
          ? '自动保存失败'
          : '已自动保存'

  return (
    <section className="case-editor" aria-labelledby="case-editor-title">
      <header className="case-editor__header">
        <div>
          <button className="text-button" type="button" onClick={() => void handleClose()}>
            ← 返回病例列表
          </button>
          <p className="eyebrow">{draft.case_code} · 草稿</p>
          <h2 id="case-editor-title">{draft.title_internal}</h2>
        </div>
        <div className="case-editor__actions">
          <span className="save-state" aria-live="polite">{saveStateText}</span>
          <button className="button" type="button" onClick={handlePublish} disabled={publishing}>
            {publishing ? '正在发布…' : '发布病例'}
          </button>
        </div>
      </header>

      {error && <p className="form-error editor-error">{error}</p>}

      <div className="case-editor__layout">
        <nav className="editor-steps" aria-label="病例编辑导航">
          <p>病例结构</p>
          {editorSections.map((section, index) => (
            <a key={section.id} href={`#${section.id}`}>
              <span>{index + 1}</span>
              {section.label}
            </a>
          ))}
        </nav>

        <div className="editor-content">
          <EditorCard id="basic-info" title="基础信息">
            <div className="form-grid">
              <label>
                病例名称（仅教师可见）
                <input value={draft.title_internal} onChange={(event) => setField('title_internal', event.target.value)} />
              </label>
              <label>
                考试限时（分钟）
                <input
                  type="number"
                  min={1}
                  max={240}
                  value={draft.time_limit_minutes}
                  onChange={(event) => setField('time_limit_minutes', Number(event.target.value))}
                />
              </label>
              <label>
                化名
                <input value={draft.patient_profile.display_name} onChange={(event) => setProfile('display_name', event.target.value)} />
              </label>
              <label>
                年龄
                <input
                  type="number"
                  min={0}
                  max={120}
                  value={draft.patient_profile.age ?? ''}
                  onChange={(event) => setProfile('age', event.target.value ? Number(event.target.value) : null)}
                />
              </label>
              <label>
                性别
                <select value={draft.patient_profile.sex} onChange={(event) => setProfile('sex', event.target.value)}>
                  <option value="unspecified">未说明</option>
                  <option value="female">女</option>
                  <option value="male">男</option>
                  <option value="other">其他</option>
                </select>
              </label>
              <label>
                职业
                <input value={draft.patient_profile.occupation} onChange={(event) => setProfile('occupation', event.target.value)} />
              </label>
              <label className="form-grid__wide">
                患者开场白(必填)
                <textarea
                  rows={4}
                  value={draft.patient_profile.opening_statement}
                  onChange={(event) => setProfile('opening_statement', event.target.value)}
                />
              </label>
            </div>
          </EditorCard>

          <EditorCard id="patient-prompt" title="AI 患者表达风格">
            <p className="section-help">
              这里只调整患者的语气、情绪、配合程度和回答习惯。事实边界、安全规则和输出格式由系统固定管理。
            </p>
            <div className="form-grid">
              <label>
                表达风格来源
                <select
                  value={draft.patient_prompt_mode}
                  onChange={(event) => setPatientPromptMode(event.target.value as CaseDraft['patient_prompt_mode'])}
                >
                  <option value="default">默认风格</option>
                  <option value="custom">当前病例自定义</option>
                </select>
              </label>
              <label className="form-grid__wide">
                患者表达风格
                <textarea
                  aria-label="患者表达风格"
                  rows={12}
                  maxLength={8000}
                  readOnly={draft.patient_prompt_mode === 'default'}
                  value={draft.patient_prompt_mode === 'default'
                    ? draft.default_patient_prompt
                    : draft.patient_prompt}
                  onChange={(event) => setPatientPrompt(event.target.value)}
                />
                <small>
                  {draft.patient_prompt_mode === 'default'
                    ? '当前病例跟随默认风格；默认风格更新后，草稿会使用新内容。'
                    : `${draft.patient_prompt.length} / 8000 字；仅影响当前病例。`}
                </small>
              </label>
            </div>
          </EditorCard>

          <EditorCard id="patient-facts" title={`患者信息 [${draft.facts.length}点]`}>
            <div className="repeat-list">
              {draft.facts.map((fact, index) => (
                <article className="repeat-item" key={fact.id ?? `fact-${index}`}>
                  <div className="repeat-item__header">
                    <strong>信息点 {index + 1}</strong>
                    <button type="button" onClick={() => setField('facts', draft.facts.filter((_, itemIndex) => itemIndex !== index))}>
                      删除
                    </button>
                  </div>
                  <div className="form-grid">
                    <label className="form-grid__wide">
                      内容
                      <textarea
                        aria-label="内容"
                        rows={3}
                        value={fact.standard_fact}
                        onChange={(event) => setField('facts', draft.facts.map((item, itemIndex) => itemIndex === index ? {
                          ...item,
                          standard_fact: event.target.value,
                          patient_expression: event.target.value,
                        } : item))}
                      />
                      <small>填写患者病情相关信息，AI 会在问诊中以患者口吻自然表达。</small>
                    </label>
                    <label>
                      披露方式
                      <select value={fact.disclosure_mode} onChange={(event) => setField('facts', draft.facts.map((item, itemIndex) => itemIndex === index ? { ...item, disclosure_mode: event.target.value } : item))}>
                        <option value="active">主动披露</option>
                        <option value="on_question">被问到后披露</option>
                        <option value="never">禁止患者披露</option>
                      </select>
                    </label>
                    <label>
                      患者确定程度
                      <select value={fact.certainty} onChange={(event) => setField('facts', draft.facts.map((item, itemIndex) => itemIndex === index ? { ...item, certainty: event.target.value } : item))}>
                        <option value="certain">确定</option>
                        <option value="vague">模糊</option>
                        <option value="forgotten">记不清</option>
                        <option value="not_understood">不理解</option>
                      </select>
                    </label>
                  </div>
                </article>
              ))}
            </div>
            <button className="button button--secondary" type="button" onClick={() => setField('facts', [...draft.facts, emptyFact(draft.facts)])}>
              添加事实信息点
            </button>
          </EditorCard>

          <EditorCard id="physical-exam" title="口腔体格检查">
            <p className="section-help">
              学生在问诊中主动申请检查后，系统会释放以下所见。文字所见是病例发布必填项。
            </p>
            <div className="form-grid">
              <label className="form-grid__wide">
                口腔体格检查所见(必填)
                <textarea
                  rows={6}
                  value={draft.physical_exam.findings_text}
                  onChange={(event) => setPhysicalExam('findings_text', event.target.value)}
                  placeholder="例如：右下后牙区牙龈红肿，局部可见瘘管……"
                />
              </label>
              <label className="form-grid__wide">
                患者同意检查时的回复
                <input
                  maxLength={500}
                  value={draft.physical_exam.consent_text}
                  onChange={(event) => setPhysicalExam('consent_text', event.target.value)}
                />
              </label>
            </div>
            <div className="physical-exam-media">
              <label className="checkbox-field physical-exam-media__confirmation">
                <input
                  type="checkbox"
                  checked={mediaConfirmed}
                  onChange={(event) => setMediaConfirmed(event.target.checked)}
                />
                我确认上传资料已获授权并完成脱敏
              </label>
              <div className="physical-exam-media__uploaders">
                <label className={`button button--secondary ${mediaBusy ? 'is-disabled' : ''}`}>
                  添加检查图片
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    multiple
                    disabled={mediaBusy}
                    onChange={(event) => void handleAssetUpload(event, 'image')}
                  />
                </label>
                <label className={`button button--secondary ${mediaBusy ? 'is-disabled' : ''}`}>
                  添加其它附件
                  <input
                    type="file"
                    multiple
                    disabled={mediaBusy}
                    onChange={(event) => void handleAssetUpload(event, 'attachment')}
                  />
                </label>
                <small>单个文件不超过 10 MB；图片可预览，其它附件仅供下载。</small>
              </div>
              {draft.physical_exam.images.length > 0 && (
                <div className="physical-exam-media__images">
                  {draft.physical_exam.images.map((asset) => (
                    <article key={asset.id}>
                      <img src={asset.content_url} alt={asset.filename} />
                      <span title={asset.filename}>{asset.filename}</span>
                      <button type="button" disabled={mediaBusy} onClick={() => void handleAssetDelete(asset.id)}>删除</button>
                    </article>
                  ))}
                </div>
              )}
              {draft.physical_exam.attachments.length > 0 && (
                <div className="physical-exam-media__attachments">
                  {draft.physical_exam.attachments.map((asset) => (
                    <article key={asset.id}>
                      <a href={asset.content_url} download>{asset.filename}</a>
                      <button type="button" disabled={mediaBusy} onClick={() => void handleAssetDelete(asset.id)}>删除</button>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </EditorCard>

          <EditorCard id="case-tests" title={`辅助检查资料（${draft.tests.length}）`}>
            <p className="section-help">配置影像学、实验室检查等需要学生在检查计划中选择的项目。</p>
            <div className="repeat-list">
              {draft.tests.map((test, index) => (
                <article className="repeat-item" key={test.id ?? `test-${index}`}>
                  <div className="repeat-item__header">
                    <strong>检查 {index + 1}</strong>
                    <button type="button" onClick={() => setField('tests', draft.tests.filter((_, itemIndex) => itemIndex !== index))}>删除</button>
                  </div>
                  <div className="form-grid">
                    <label>检查编码<input value={test.code} onChange={(event) => setField('tests', draft.tests.map((item, itemIndex) => itemIndex === index ? { ...item, code: event.target.value } : item))} /></label>
                    <label>检查名称<input value={test.name} onChange={(event) => setField('tests', draft.tests.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item))} /></label>
                    <label className="form-grid__wide">向学生释放的结果<textarea rows={3} value={test.result_text} onChange={(event) => setField('tests', draft.tests.map((item, itemIndex) => itemIndex === index ? { ...item, result_text: event.target.value } : item))} /></label>
                    <label className="form-grid__wide">教师标准解读<textarea rows={3} value={test.teacher_interpretation} onChange={(event) => setField('tests', draft.tests.map((item, itemIndex) => itemIndex === index ? { ...item, teacher_interpretation: event.target.value } : item))} /></label>
                  </div>
                </article>
              ))}
            </div>
            <button className="button button--secondary" type="button" onClick={() => setField('tests', [...draft.tests, emptyTest(draft.tests.length)])}>添加检查</button>
          </EditorCard>

          <EditorCard id="diagnosis-rules" title={`诊断规则（${draft.diagnosis_rules.length}）`}>
            <div className="repeat-list">
              {draft.diagnosis_rules.map((rule, index) => (
                <article className="repeat-item" key={rule.id ?? `diagnosis-${index}`}>
                  <div className="repeat-item__header"><strong>诊断 {index + 1}</strong><button type="button" onClick={() => setField('diagnosis_rules', draft.diagnosis_rules.filter((_, itemIndex) => itemIndex !== index))}>删除</button></div>
                  <div className="form-grid">
                    <label>类型<select value={rule.diagnosis_type} onChange={(event) => setField('diagnosis_rules', draft.diagnosis_rules.map((item, itemIndex) => itemIndex === index ? { ...item, diagnosis_type: event.target.value } : item))}><option value="initial">初步诊断</option><option value="differential">鉴别诊断</option><option value="final">最终诊断</option></select></label>
                    <label>诊断名称<input value={rule.name} onChange={(event) => setField('diagnosis_rules', draft.diagnosis_rules.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item))} /></label>
                    <label>可接受同义词<DelimitedListInput value={rule.aliases} onChange={(value) => setField('diagnosis_rules', draft.diagnosis_rules.map((item, itemIndex) => itemIndex === index ? { ...item, aliases: value } : item))} /></label>
                    <label>支持证据<DelimitedListInput value={rule.supporting_evidence} onChange={(value) => setField('diagnosis_rules', draft.diagnosis_rules.map((item, itemIndex) => itemIndex === index ? { ...item, supporting_evidence: value } : item))} /></label>
                  </div>
                </article>
              ))}
            </div>
            <button className="button button--secondary" type="button" onClick={() => setField('diagnosis_rules', [...draft.diagnosis_rules, emptyDiagnosis(draft.diagnosis_rules.length)])}>添加诊断规则</button>
          </EditorCard>

          <EditorCard id="scoring-rules" title={`评分规则（${draft.scoring_items.length}）`}>
            <div className="repeat-list">
              {draft.scoring_items.map((item, index) => (
                <article className="repeat-item" key={item.id ?? `score-${index}`}>
                  <div className="repeat-item__header"><strong>评分项 {index + 1}</strong><button type="button" onClick={() => setField('scoring_items', draft.scoring_items.filter((_, itemIndex) => itemIndex !== index))}>删除</button></div>
                  <div className="form-grid">
                    <label>评分编码<input value={item.code} onChange={(event) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, code: event.target.value } : score))} /></label>
                    <label>评分名称<input value={item.label} onChange={(event) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, label: event.target.value } : score))} /></label>
                    <label>维度<select value={item.dimension} onChange={(event) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, dimension: event.target.value } : score))}><option value="history">病史采集</option><option value="communication">沟通</option><option value="summary">病史摘要</option><option value="clinical">临床表现</option><option value="differential">鉴别诊断</option><option value="test_plan">检查计划</option><option value="final_reasoning">最终诊断</option></select></label>
                    <label>满分<input type="number" min={0} step="0.5" value={item.max_score} onChange={(event) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, max_score: event.target.value } : score))} /></label>
                    <label>
                      评价方式
                      <select value={item.evaluation_method} onChange={(event) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, evaluation_method: event.target.value } : score))}>
                        <option value="rule">确定性规则</option>
                        <option value="teacher">教师评价（暂标记待评价）</option>
                      </select>
                    </label>
                    {item.evaluation_method === 'rule' && (
                      <label>
                        规则依据
                        <select
                          value={String(item.matching_config.source ?? '')}
                          onChange={(event) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, matching_config: { source: event.target.value } } : score))}
                        >
                          <option value="">请选择</option>
                          <option value="history_facts">问诊事实点</option>
                          <option value="diagnoses">诊断名称</option>
                          <option value="tests">检查项目</option>
                          <option value="physical_exam_request">体格检查申请</option>
                          <option value="submission_keywords">阶段答案关键词</option>
                        </select>
                      </label>
                    )}
                    {item.evaluation_method === 'rule' && item.matching_config.source === 'history_facts' && (
                      <label className="form-grid__wide">病情信息编码（逗号分隔）<DelimitedListInput value={Array.isArray(item.matching_config.fact_codes) ? item.matching_config.fact_codes : []} onChange={(value) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, matching_config: { ...score.matching_config, fact_codes: value } } : score))} /></label>
                    )}
                    {item.evaluation_method === 'rule' && item.matching_config.source === 'diagnoses' && (
                      <label className="form-grid__wide">标准诊断名称（逗号分隔；留空时按维度匹配必需诊断）<DelimitedListInput value={Array.isArray(item.matching_config.diagnosis_names) ? item.matching_config.diagnosis_names : []} onChange={(value) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, matching_config: { ...score.matching_config, diagnosis_names: value } } : score))} /></label>
                    )}
                    {item.evaluation_method === 'rule' && item.matching_config.source === 'tests' && (
                      <label className="form-grid__wide">检查编码（逗号分隔；留空时匹配所有需主动申请的检查）<DelimitedListInput value={Array.isArray(item.matching_config.test_codes) ? item.matching_config.test_codes : []} onChange={(value) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, matching_config: { ...score.matching_config, test_codes: value } } : score))} /></label>
                    )}
                    {item.evaluation_method === 'rule' && item.matching_config.source === 'submission_keywords' && (
                      <>
                        <label>答案阶段<select value={String(item.matching_config.submission_type ?? '')} onChange={(event) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, matching_config: { ...score.matching_config, submission_type: event.target.value } } : score))}><option value="">请选择</option><option value="history_summary">病史摘要</option><option value="initial_reasoning">初步判断</option><option value="test_selection">检查计划</option><option value="final_reasoning">最终判断</option></select></label>
                        <label>命中方式<select value={String(item.matching_config.match ?? 'all')} onChange={(event) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, matching_config: { ...score.matching_config, match: event.target.value } } : score))}><option value="all">按命中比例评分</option><option value="any">命中任一即满分</option></select></label>
                        <label className="form-grid__wide">关键词（逗号分隔）<DelimitedListInput value={Array.isArray(item.matching_config.keywords) ? item.matching_config.keywords : []} onChange={(value) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, matching_config: { ...score.matching_config, keywords: value } } : score))} /></label>
                      </>
                    )}
                    <label className="form-grid__wide">评分说明<textarea rows={2} value={item.description} onChange={(event) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, description: event.target.value } : score))} /></label>
                    <label className="form-grid__wide">学生可见反馈<textarea rows={2} value={item.student_feedback} onChange={(event) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, student_feedback: event.target.value } : score))} /></label>
                    <label className="checkbox-field"><input type="checkbox" checked={item.is_student_visible} onChange={(event) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, is_student_visible: event.target.checked } : score))} />学生反馈中显示该评分项</label>
                  </div>
                </article>
              ))}
            </div>
            <button className="button button--secondary" type="button" onClick={() => setField('scoring_items', [...draft.scoring_items, emptyScoringItem(draft.scoring_items.length)])}>添加评分项</button>
          </EditorCard>
        </div>
      </div>
    </section>
  )
}
