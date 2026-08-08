import { ReactNode, useEffect, useState } from 'react'

import {
  ApiError,
  CaseDraft,
  CaseFact,
  CaseTest,
  DiagnosisRule,
  publishCase,
  saveCaseDraft,
  ScoringItem,
} from '../api/client'

const steps = ['教学设置', '患者身份', '患者事实', '检查资料', '诊断规则', '评分规则', '预览发布']

const emptyFact = (order: number): CaseFact => ({
  code: `fact.${order + 1}`,
  category: 'present_illness',
  standard_fact: '',
  patient_expression: '',
  semantic_tags: [],
  synonyms: [],
  disclosure_mode: 'on_question',
  certainty: 'certain',
  unknown_response: '这个我不太清楚。',
  is_required: false,
  score: '0.00',
  teacher_notes: '',
  display_order: order,
})

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

function EditorCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="editor-card">
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
  const [step, setStep] = useState(0)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  function setField<K extends keyof CaseDraft>(field: K, value: CaseDraft[K]) {
    setDraft((current) => ({ ...current, [field]: value }))
  }

  function setProfile(field: keyof CaseDraft['patient_profile'], value: string | number | null) {
    setDraft((current) => ({
      ...current,
      patient_profile: { ...current.patient_profile, [field]: value },
    }))
  }

  function stepPayload(): Partial<CaseDraft> {
    if (step === 0) {
      return {
        title_internal: draft.title_internal,
        specialty: draft.specialty,
        disease_tags: draft.disease_tags,
        difficulty: draft.difficulty,
        estimated_minutes: draft.estimated_minutes,
        teaching_objectives: draft.teaching_objectives,
        target_grade: draft.target_grade,
        is_exam_mode: draft.is_exam_mode,
        time_limit_minutes: draft.time_limit_minutes,
        enabled_stages: draft.enabled_stages,
      }
    }
    if (step === 1) return { patient_profile: draft.patient_profile }
    if (step === 2) return { facts: draft.facts }
    if (step === 3) return { tests: draft.tests }
    if (step === 4) return { diagnosis_rules: draft.diagnosis_rules }
    if (step === 5) return { scoring_items: draft.scoring_items }
    return {}
  }

  async function saveCurrentStep(): Promise<boolean> {
    if (step === 6) return true
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const updated = await saveCaseDraft(draft.case_id, {
        ...stepPayload(),
        expected_updated_at: draft.updated_at,
      })
      setDraft(updated)
      setMessage('草稿已保存')
      return true
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '保存失败，请稍后重试。')
      return false
    } finally {
      setSaving(false)
    }
  }

  async function moveNext() {
    if (await saveCurrentStep()) setStep((current) => Math.min(current + 1, steps.length - 1))
  }

  async function handlePublish() {
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const result = await publishCase(draft.case_id)
      setMessage(
        result.created
          ? `病例 v${result.version.version_number} 已发布，后续编辑不会改变该版本。`
          : `当前内容与 v${result.version.version_number} 相同，无需重复发布。`,
      )
    } catch (requestError: unknown) {
      setError(requestError instanceof ApiError ? requestError.message : '发布失败，请稍后重试。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="case-editor" aria-labelledby="case-editor-title">
      <header className="case-editor__header">
        <div>
          <button className="text-button" type="button" onClick={onClose}>
            ← 返回病例列表
          </button>
          <p className="eyebrow">{draft.case_code} · 草稿</p>
          <h2 id="case-editor-title">{draft.title_internal}</h2>
        </div>
        <span className="save-state">{saving ? '正在保存…' : message || '所有修改仅保存到草稿'}</span>
      </header>

      <nav className="editor-steps" aria-label="病例编辑步骤">
        {steps.map((label, index) => (
          <button
            key={label}
            type="button"
            className={index === step ? 'is-active' : index < step ? 'is-complete' : ''}
            onClick={() => setStep(index)}
          >
            <span>{index + 1}</span>
            {label}
          </button>
        ))}
      </nav>

      <div className="editor-content">
        {step === 0 && (
          <EditorCard title="教学设置">
            <div className="form-grid">
              <label>
                病例名称（仅教师可见）
                <input value={draft.title_internal} onChange={(event) => setField('title_internal', event.target.value)} />
              </label>
              <label>
                专业方向
                <input value={draft.specialty} onChange={(event) => setField('specialty', event.target.value)} />
              </label>
              <label>
                病种标签（逗号分隔，仅教师可见）
                <DelimitedListInput
                  value={draft.disease_tags}
                  onChange={(value) => setField('disease_tags', value)}
                />
              </label>
              <label>
                难度
                <select value={draft.difficulty} onChange={(event) => setField('difficulty', event.target.value)}>
                  <option value="basic">基础</option>
                  <option value="intermediate">中级</option>
                  <option value="advanced">高级</option>
                </select>
              </label>
              <label>
                预计完成时间（分钟）
                <input
                  type="number"
                  min={1}
                  max={240}
                  value={draft.estimated_minutes}
                  onChange={(event) => setField('estimated_minutes', Number(event.target.value))}
                />
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
                适用年级
                <input value={draft.target_grade} onChange={(event) => setField('target_grade', event.target.value)} />
              </label>
              <label className="form-grid__wide">
                教学目标
                <textarea
                  rows={4}
                  value={draft.teaching_objectives}
                  onChange={(event) => setField('teaching_objectives', event.target.value)}
                />
              </label>
            </div>
          </EditorCard>
        )}

        {step === 1 && (
          <EditorCard title="患者身份与表达方式">
            <div className="form-grid">
              <label>
                教学化名
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
              <label>
                性格与配合程度
                <input value={draft.patient_profile.personality} onChange={(event) => setProfile('personality', event.target.value)} />
              </label>
              <label>
                当前情绪
                <input value={draft.patient_profile.emotion} onChange={(event) => setProfile('emotion', event.target.value)} />
              </label>
              <label className="form-grid__wide">
                患者开场白（发布必填）
                <textarea
                  rows={4}
                  value={draft.patient_profile.opening_statement}
                  onChange={(event) => setProfile('opening_statement', event.target.value)}
                />
              </label>
            </div>
          </EditorCard>
        )}

        {step === 2 && (
          <EditorCard title={`患者事实库（${draft.facts.length}）`}>
            <p className="section-help">每个事实都是独立信息点。AI 只能围绕这些事实回答，未定义内容不得补齐。</p>
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
                    <label>
                      信息点编码
                      <input value={fact.code} onChange={(event) => setField('facts', draft.facts.map((item, itemIndex) => itemIndex === index ? { ...item, code: event.target.value } : item))} />
                    </label>
                    <label>
                      分类
                      <select value={fact.category} onChange={(event) => setField('facts', draft.facts.map((item, itemIndex) => itemIndex === index ? { ...item, category: event.target.value } : item))}>
                        <option value="chief_complaint">主诉</option>
                        <option value="present_illness">现病史</option>
                        <option value="past_history">既往史</option>
                        <option value="medication">用药史</option>
                        <option value="allergy">过敏史</option>
                        <option value="personal">个人史</option>
                        <option value="family">家族史</option>
                        <option value="concern">患者担忧</option>
                        <option value="other">其他</option>
                      </select>
                    </label>
                    <label className="form-grid__wide">
                      标准事实
                      <textarea rows={2} value={fact.standard_fact} onChange={(event) => setField('facts', draft.facts.map((item, itemIndex) => itemIndex === index ? { ...item, standard_fact: event.target.value } : item))} />
                    </label>
                    <label className="form-grid__wide">
                      患者口语表达
                      <textarea rows={2} value={fact.patient_expression} onChange={(event) => setField('facts', draft.facts.map((item, itemIndex) => itemIndex === index ? { ...item, patient_expression: event.target.value } : item))} />
                    </label>
                    <label>
                      语义路由提示词（可选，逗号分隔）
                      <DelimitedListInput value={fact.semantic_tags} onChange={(value) => setField('facts', draft.facts.map((item, itemIndex) => itemIndex === index ? { ...item, semantic_tags: value } : item))} />
                    </label>
                    <label>
                      典型同义问法（可选，逗号分隔）
                      <DelimitedListInput value={fact.synonyms} onChange={(value) => setField('facts', draft.facts.map((item, itemIndex) => itemIndex === index ? { ...item, synonyms: value } : item))} />
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
                    <label className="form-grid__wide">
                      病例未提供时的回答
                      <input value={fact.unknown_response} onChange={(event) => setField('facts', draft.facts.map((item, itemIndex) => itemIndex === index ? { ...item, unknown_response: event.target.value } : item))} />
                    </label>
                    <label>
                      事实点分值
                      <input type="number" min="0" step="0.5" value={fact.score} onChange={(event) => setField('facts', draft.facts.map((item, itemIndex) => itemIndex === index ? { ...item, score: event.target.value } : item))} />
                    </label>
                    <label className="checkbox-field">
                      <input type="checkbox" checked={fact.is_required} onChange={(event) => setField('facts', draft.facts.map((item, itemIndex) => itemIndex === index ? { ...item, is_required: event.target.checked } : item))} />
                      必问信息点
                    </label>
                  </div>
                </article>
              ))}
            </div>
            <button className="button button--secondary" type="button" onClick={() => setField('facts', [...draft.facts, emptyFact(draft.facts.length)])}>
              添加事实信息点
            </button>
          </EditorCard>
        )}

        {step === 3 && (
          <EditorCard title={`检查资料（${draft.tests.length}）`}>
            <p className="section-help">文字检查结果为主，图片和附件后续可选添加。</p>
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
        )}

        {step === 4 && (
          <EditorCard title={`诊断规则（${draft.diagnosis_rules.length}）`}>
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
        )}

        {step === 5 && (
          <EditorCard title={`评分规则（${draft.scoring_items.length}）`}>
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
                        <option value="ai">AI 辅助评价</option>
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
                          <option value="submission_keywords">阶段答案关键词</option>
                        </select>
                      </label>
                    )}
                    {item.evaluation_method === 'rule' && item.matching_config.source === 'history_facts' && (
                      <label className="form-grid__wide">患者事实编码（逗号分隔）<DelimitedListInput value={Array.isArray(item.matching_config.fact_codes) ? item.matching_config.fact_codes : []} onChange={(value) => setField('scoring_items', draft.scoring_items.map((score, itemIndex) => itemIndex === index ? { ...score, matching_config: { ...score.matching_config, fact_codes: value } } : score))} /></label>
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
        )}

        {step === 6 && (
          <EditorCard title="发布前检查">
            <div className="publish-summary">
              <div><strong>{draft.facts.length}</strong><span>患者事实</span></div>
              <div><strong>{draft.tests.length}</strong><span>检查资料</span></div>
              <div><strong>{draft.diagnosis_rules.length}</strong><span>诊断规则</span></div>
              <div><strong>{draft.scoring_items.length}</strong><span>评分项</span></div>
            </div>
            <ul className="release-checklist">
              <li className={draft.patient_profile.opening_statement ? 'is-ready' : ''}>患者开场白已填写</li>
              <li className={draft.facts.length > 0 ? 'is-ready' : ''}>至少包含一个患者事实</li>
              <li>发布后生成不可变版本；草稿仍可继续编辑并发布下一版</li>
              <li>学生在教师统一发布反馈前看不到诊断和标准答案</li>
            </ul>
            <button className="button" type="button" onClick={handlePublish} disabled={saving}>发布不可变版本</button>
          </EditorCard>
        )}
      </div>

      {error && <p className="form-error editor-error">{error}</p>}
      <footer className="editor-actions">
        <button className="button button--secondary" type="button" disabled={step === 0 || saving} onClick={() => setStep((current) => current - 1)}>上一步</button>
        {step < steps.length - 1 && (
          <>
            <button className="button button--secondary" type="button" disabled={saving} onClick={saveCurrentStep}>保存草稿</button>
            <button className="button" type="button" disabled={saving} onClick={moveNext}>保存并继续</button>
          </>
        )}
      </footer>
    </section>
  )
}
