export type UserRole = 'student' | 'teacher' | 'administrator'

export type CurrentUser = {
  id: string
  email: string
  display_name: string
  roles: UserRole[]
  class_names: string[]
}

type AuthPayload = {
  email: string
  password: string
}

type RegistrationPayload = AuthPayload & {
  display_name: string
  class_group_id: string
  verification_code: string
}

export type RegistrationClass = {
  id: string
  code: string
  name: string
  teacher_name: string
}

export type PatientProfile = {
  id?: number
  display_name: string
  age: number | null
  sex: 'female' | 'male' | 'other' | 'unspecified'
  occupation: string
  education: string
  personality: string
  emotion: string
  cooperation: string
  medical_literacy: string
  opening_statement: string
  avatar_asset_id: string
  voice_id: string
}

export type CaseFact = {
  id?: number
  code: string
  standard_fact: string
  patient_expression: string
  disclosure_mode: string
  certainty: string
  teacher_notes: string
  display_order: number
}

export type CaseTest = {
  id?: number
  code: string
  name: string
  category: string
  student_description: string
  result_text: string
  teacher_interpretation: string
  release_stage: string
  requires_request: boolean
  prerequisite_code: string
  display_order: number
}

export type PhysicalExamAsset = {
  id: number
  kind: 'image' | 'attachment'
  display_order?: number
  filename: string
  content_type: string
  size_bytes: number
  deidentified_confirmed?: boolean
  content_url: string
}

export type PhysicalExam = {
  findings_text: string
  consent_text: string
  images: PhysicalExamAsset[]
  attachments: PhysicalExamAsset[]
}

export type DiagnosisRule = {
  id?: number
  diagnosis_type: string
  name: string
  aliases: string[]
  supporting_evidence: string[]
  opposing_evidence: string[]
  is_required: boolean
  display_order: number
}

export type ScoringItem = {
  id?: number
  code: string
  dimension: string
  label: string
  description: string
  max_score: string
  evaluation_method: string
  matching_config: Record<string, unknown>
  student_feedback: string
  teacher_notes: string
  is_student_visible: boolean
  display_order: number
}

export type CaseDraft = {
  id: string
  case_id: string
  case_code: string
  status: 'draft'
  version_number: null
  title_internal: string
  difficulty: string
  is_exam_mode: boolean
  time_limit_minutes: number
  enabled_stages: string[]
  patient_prompt_mode: 'default' | 'custom'
  patient_prompt: string
  effective_patient_prompt: string
  default_patient_prompt: string
  patient_questions_enabled: boolean
  patient_questions_mode: 'default' | 'custom'
  patient_questions: PatientQuestionItem[]
  effective_patient_questions: PatientQuestionItem[]
  default_patient_questions: PatientQuestionItem[]
  created_at: string
  updated_at: string
  patient_profile: PatientProfile
  physical_exam: PhysicalExam
  facts: CaseFact[]
  tests: CaseTest[]
  diagnosis_rules: DiagnosisRule[]
  scoring_items: ScoringItem[]
}

export type PatientPromptTemplate = {
  id: number
  name: string
  content: string
  updated_by_name: string
  updated_at: string
}

export type PatientQuestionItem = {
  id: string
  base_question: string
  answer_criteria: string
  enabled: boolean
}

export type PatientQuestionTemplate = {
  id: number
  name: string
  questions: PatientQuestionItem[]
  updated_by_name: string
  updated_at: string
}

export type CaseSummary = {
  id: string
  code: string
  is_active: boolean
  created_at: string
  draft: {
    id: string
    title_internal: string
    updated_at: string
  } | null
  latest_published: {
    id: string
    version_number: number
    published_at: string
  } | null
}

export type AttemptStatus = 'not_started' | 'active' | 'completed' | 'expired'

export type StudentAssignment = {
  id: string
  title: string
  difficulty: 'basic' | 'intermediate' | 'advanced'
  duration_minutes: number
  opens_at: string
  deadline_at: string
  status: 'open' | 'closed'
  feedback_released_at: string | null
  attempt_status: AttemptStatus
  session_id: string | null
}

export type SessionStage =
  | 'interview'
  | 'completed'

export type SessionMessage = {
  id: string
  sequence: number
  role: 'student' | 'patient' | 'system'
  kind: 'chat' | 'physical_exam_consent' | 'physical_exam_result' | 'patient_initiated_question' | 'patient_reaction'
  content: string
  client_message_id: string
  reply_to_id: string | null
  response_status: 'processing' | 'completed' | 'failed' | 'not_applicable'
  error_code: string
  created_at: string
}

export type PatientInitiativeState = {
  enabled: boolean
  phase: 'inactive' | 'idle' | 'awaiting_student' | 'complete'
  activated_at: string | null
  next_due_at: string | null
  active_message_id: string | null
}

export type PhysicalExamResult = {
  release_id: string | null
  released_at: string | null
  access_reason: 'triggered' | 'feedback' | 'teacher'
  findings_text: string
  images: PhysicalExamAsset[]
  attachments: PhysicalExamAsset[]
}

export type StudentCaseDraft = {
  chief_complaint: string
  present_illness: string
  past_history: string
  family_history: string
  diagnosis: string
  treatment: string
  medical_advice: string
}

export type StudentCaseRecord = StudentCaseDraft & {
  specialty_exam: string
  submitted_at: string
}

export type SimulationSession = {
  id: string
  assignment_id: string
  assignment_title: string
  patient_name: string
  opening_statement: string
  status: 'active' | 'completed' | 'expired'
  stage: SessionStage
  started_at: string
  deadline_at: string
  completed_at: string | null
  remaining_seconds: number
  messages: SessionMessage[]
  case_draft: StudentCaseDraft
  case_draft_revision: number
  case_record: StudentCaseRecord | null
  physical_exam_result: PhysicalExamResult | null
  patient_initiative: PatientInitiativeState
}

export type SessionFeedback = {
  session_id: string
  standard_diagnoses: Array<{
    type: string
    name: string
    supporting_evidence: string[]
  }>
  standard_tests: Array<{
    code: string
    name: string
    result: string
    interpretation: string
  }>
  score: AssessmentScore
  scoring_items: ScoreResult[]
  omissions: FeedbackIssue[]
  errors: FeedbackIssue[]
  feedback_summary: string
  ai_feedback: string | null
  teacher_comment: string
  physical_exam_result: PhysicalExamResult | null
}

export type AssessmentScore = {
  automatic_score: number
  final_score: number
  scored_maximum: number
  maximum_score: number
  provisional: boolean
}

export type FeedbackIssue = {
  code: string
  label: string
  reason: string
  standard_answer: string
}

export type ScoreResult = {
  id?: string
  code: string
  label: string
  dimension: string
  evaluation_method?: string
  automatic_score: number | null
  ai_score: number | null
  ai_confidence: number | null
  ai_reason: string
  ai_feedback: string
  ai_evidence_excerpt: string
  teacher_score: number | null
  effective_score: number | null
  adjustment_reason: string
  max_score: number
  decision: 'achieved' | 'partial' | 'missed' | 'pending'
  effective_decision: 'achieved' | 'partial' | 'missed' | 'pending'
  confidence?: number | null
  evidence_message_ids?: string[]
  evidence_submission_ids?: string[]
  evidence_excerpt: string
  standard_answer: string
  reason: string
  is_student_visible?: boolean
  rule_version?: string
  model_version?: string
}

export type SessionAssessment = AssessmentScore & {
  omissions: FeedbackIssue[]
  errors: FeedbackIssue[]
  feedback_summary: string
  ai_feedback: string
  scoring_version: string
  generated_at: string
  scoring_items: ScoreResult[]
}

export type TeacherResponseRow = {
  student_id: string
  display_name: string
  email: string
  attempt_status: AttemptStatus
  session_id: string | null
  started_at: string | null
  completed_at: string | null
  elapsed_seconds: number | null
  score: AssessmentScore | null
}

export type AssignmentStatistics = {
  summary: {
    student_count: number
    started_count: number
    completed_count: number
    expired_count: number
    assessed_count: number
    completion_rate: number
    average_score: number | null
    average_score_percentage: number | null
    average_duration_seconds: number | null
  }
  frequent_omissions: Array<{
    code: string
    label: string
    count: number
    rate: number
  }>
  common_errors: Array<{
    code: string
    label: string
    count: number
    rate: number
  }>
}

export type TeacherReview = {
  id: string
  revision: number
  reviewer_id: string
  reviewer_name: string
  score_overrides: Record<string, { score: string | null; reason: string }>
  comment: string
  final_score: number
  scored_maximum: number
  maximum_score: number
  provisional: boolean
  created_at: string
}

export type AIEvaluationRun = {
  id: string
  status: 'running' | 'succeeded' | 'failed'
  requested_by_id: string
  requested_by_name: string
  provider: string
  model: string
  resolved_model: string
  prompt_version: string
  scoring_item_codes: string[]
  feedback_summary: string
  latency_ms: number
  input_tokens: number | null
  output_tokens: number | null
  error_code: string
  created_at: string
  completed_at: string | null
  results: Array<{
    code: string
    label: string
    score: number
    max_score: number
    decision: 'achieved' | 'partial' | 'missed'
    confidence: number
    evidence_message_ids: string[]
    evidence_submission_ids: string[]
    evidence_excerpt: string
    reason: string
    feedback: string
  }>
}

export type TeacherSessionRecord = SimulationSession & {
  student_id: string
  student_name: string
  student_email: string
  assessment: SessionAssessment | null
  latest_review: TeacherReview | null
  ai_evaluation: AIEvaluationRun | null
  standard_diagnoses: SessionFeedback['standard_diagnoses']
  standard_tests: SessionFeedback['standard_tests']
}

export type RosterStudent = {
  id: string
  email: string
  display_name: string
  created_at: string
}

export type TeachingClass = {
  id: string
  code: string
  name: string
  created_by_name: string
  is_active: boolean
  student_count: number
  students: RosterStudent[]
  created_at: string
}

export type ManagedStudent = {
  id: string
  display_name: string
  email: string
  classes: Array<{
    id: string
    code: string
    name: string
    is_active: boolean
  }>
  is_active: boolean
  date_joined: string
}

export type ManagedStudentFilters = {
  name?: string
  email?: string
  class_group_id?: string
}

export type TeacherAssignment = {
  id: string
  title: string
  case_version_id: string
  class_group_id: string
  case_title: string
  case_version_number: number
  class_code: string
  class_name: string
  duration_minutes: number
  opens_at: string
  deadline_at: string
  status: 'open' | 'closed'
  feedback_released_at: string | null
  student_count: number
  not_started_count: number
  active_count: number
  submitted_count: number
  expired_count: number
  created_at: string
}

export type AssignmentOptions = {
  case_versions: Array<{
    id: string
    case_code: string
    title: string
    version_number: number
    suggested_duration_minutes: number
  }>
  class_groups: Array<{
    id: string
    class_code: string
    class_name: string
    student_count: number
  }>
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly details?: unknown,
    readonly requestId?: string,
  ) {
    super(message)
  }
}

const validationFieldLabels: Record<string, string> = {
  patient_profile: '患者身份',
  facts: '病情信息',
  physical_exam: '口腔体格检查',
  tests: '辅助检查资料',
  diagnosis_rules: '诊断规则',
  scoring_items: '评分规则',
  title_internal: '病例名称',
  time_limit_minutes: '考试限时',
  enabled_stages: '病例阶段',
  patient_prompt_mode: '提示词来源',
  patient_prompt: '患者问诊提示词',
  patient_questions_enabled: '患者主动提问开关',
  patient_questions_mode: '主动问题来源',
  patient_questions: '患者主动问题',
  base_question: '基础问法',
  answer_criteria: '实质回应判定要点',
  display_name: '化名',
  age: '年龄',
  sex: '性别',
  occupation: '职业',
  personality: '性格与配合程度',
  emotion: '当前情绪',
  opening_statement: '患者开场白',
  findings_text: '体格检查所见',
  consent_text: '患者同意语',
  code: '编码',
  category: '分类',
  standard_fact: '内容',
  patient_expression: '内容',
  disclosure_mode: '披露方式',
  certainty: '患者确定程度',
  name: '名称',
  result_text: '向学生释放的结果',
  teacher_interpretation: '教师标准解读',
  diagnosis_type: '诊断类型',
  aliases: '可接受同义词',
  supporting_evidence: '支持证据',
  label: '评分名称',
  dimension: '评分维度',
  max_score: '满分',
  evaluation_method: '评价方式',
  matching_config: '规则依据',
}

const contextualValidationFieldLabels: Record<string, string> = {
  'facts.code': '信息点编码',
  'tests.code': '检查编码',
  'tests.name': '检查名称',
  'diagnosis_rules.name': '诊断名称',
  'scoring_items.code': '评分编码',
  'scoring_items.label': '评分名称',
}

type ValidationErrorPath = Array<string | number>

function validationErrorPathLabel(path: ValidationErrorPath): string {
  const labels: string[] = []
  const root = typeof path[0] === 'string' ? path[0] : ''
  for (const segment of path) {
    if (typeof segment === 'number') {
      const lastIndex = labels.length - 1
      if (lastIndex >= 0) labels[lastIndex] = `${labels[lastIndex]} ${segment + 1}`
      continue
    }
    if (segment === 'non_field_errors') continue
    labels.push(
      contextualValidationFieldLabels[`${root}.${segment}`]
      ?? validationFieldLabels[segment]
      ?? segment,
    )
  }
  return labels.join(' / ') || '请求内容'
}

function collectValidationErrors(value: unknown, path: ValidationErrorPath = []): string[] {
  if (typeof value === 'string') {
    return [`${validationErrorPathLabel(path)}：${value}`]
  }
  if (Array.isArray(value)) {
    return value.flatMap((item, index) => (
      typeof item === 'string'
        ? collectValidationErrors(item, path)
        : collectValidationErrors(item, [...path, index])
    ))
  }
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .filter(([key]) => key !== 'detail' && key !== 'request_id')
      .flatMap(([key, item]) => collectValidationErrors(item, [...path, key]))
  }
  return []
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T

  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    let message = '请求失败，请稍后重试。'
    let bodyRequestId = ''
    if (data && typeof data === 'object') {
      const record = data as Record<string, unknown>
      if (typeof record.detail === 'string') message = record.detail
      if (typeof record.request_id === 'string') bodyRequestId = record.request_id
      if (message === '请求失败，请稍后重试。') {
        const validationErrors = [...new Set(collectValidationErrors(record))]
        if (validationErrors.length > 0) message = validationErrors.join('；')
      }
    }
    const requestId = response.headers.get('X-Request-ID') || bodyRequestId
    const displayMessage = response.status >= 500 && requestId
      ? `${message}（问题编号：${requestId}）`
      : message
    throw new ApiError(displayMessage, response.status, data, requestId || undefined)
  }
  return data as T
}

async function getCsrfToken(): Promise<string> {
  const response = await fetch('/api/auth/csrf/', {
    credentials: 'same-origin',
  })
  const data = await parseResponse<{ csrf_token: string }>(response)
  return data.csrf_token
}

async function mutate<T>(
  method: 'POST' | 'PATCH' | 'DELETE',
  path: string,
  payload?: unknown,
): Promise<T> {
  const csrfToken = await getCsrfToken()
  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
  return parseResponse<T>(response)
}

async function mutateForm<T>(path: string, payload: FormData): Promise<T> {
  const csrfToken = await getCsrfToken()
  const response = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': csrfToken },
    body: payload,
  })
  return parseResponse<T>(response)
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const response = await fetch('/api/auth/me/', { credentials: 'same-origin' })
  return parseResponse<CurrentUser>(response)
}

export function register(payload: RegistrationPayload): Promise<CurrentUser> {
  return mutate<CurrentUser>('POST', '/api/auth/register/', payload)
}

export function requestRegistrationCode(email: string): Promise<{ detail: string; expires_in: number }> {
  return mutate('POST', '/api/auth/verification-codes/registration/', { email })
}

export function requestPasswordResetCode(email: string): Promise<{ detail: string }> {
  return mutate('POST', '/api/auth/verification-codes/password-reset/', { email })
}

export function resetPassword(payload: {
  email: string
  verification_code: string
  new_password: string
}): Promise<{ detail: string }> {
  return mutate('POST', '/api/auth/password-reset/', payload)
}

export async function listRegistrationClasses(): Promise<RegistrationClass[]> {
  const response = await fetch('/api/auth/registration-classes/', {
    credentials: 'same-origin',
  })
  return parseResponse<RegistrationClass[]>(response)
}

export function signIn(payload: AuthPayload): Promise<CurrentUser> {
  return mutate<CurrentUser>('POST', '/api/auth/login/', payload)
}

export function signOut(): Promise<void> {
  return mutate<void>('POST', '/api/auth/logout/')
}

export async function listTeacherCases(): Promise<CaseSummary[]> {
  const response = await fetch('/api/teacher/cases/', { credentials: 'same-origin' })
  return parseResponse<CaseSummary[]>(response)
}

export function createTeacherCase(): Promise<CaseDraft> {
  return mutate<CaseDraft>('POST', '/api/teacher/cases/', {})
}

export async function getPatientPromptTemplate(): Promise<PatientPromptTemplate> {
  const response = await fetch('/api/teacher/cases/patient-prompt-template/', {
    credentials: 'same-origin',
  })
  return parseResponse<PatientPromptTemplate>(response)
}

export function savePatientPromptTemplate(content: string): Promise<PatientPromptTemplate> {
  return mutate<PatientPromptTemplate>(
    'PATCH',
    '/api/teacher/cases/patient-prompt-template/',
    { content },
  )
}

export async function getPatientQuestionTemplate(): Promise<PatientQuestionTemplate> {
  const response = await fetch('/api/teacher/cases/patient-question-template/', {
    credentials: 'same-origin',
  })
  return parseResponse<PatientQuestionTemplate>(response)
}

export function savePatientQuestionTemplate(
  questions: PatientQuestionItem[],
): Promise<PatientQuestionTemplate> {
  return mutate<PatientQuestionTemplate>(
    'PATCH',
    '/api/teacher/cases/patient-question-template/',
    { questions },
  )
}

export async function getCaseDraft(caseId: string): Promise<CaseDraft> {
  const response = await fetch(`/api/teacher/cases/${caseId}/draft/`, {
    credentials: 'same-origin',
  })
  return parseResponse<CaseDraft>(response)
}

export function saveCaseDraft(
  caseId: string,
  payload: Partial<CaseDraft> & { expected_updated_at: string },
): Promise<CaseDraft> {
  return mutate<CaseDraft>('PATCH', `/api/teacher/cases/${caseId}/draft/`, payload)
}

export function uploadPhysicalExamAsset(
  caseId: string,
  payload: {
    file: File
    kind: 'image' | 'attachment'
    deidentified_confirmed: boolean
    expected_updated_at: string
  },
): Promise<CaseDraft> {
  const form = new FormData()
  form.append('file', payload.file)
  form.append('kind', payload.kind)
  form.append('deidentified_confirmed', String(payload.deidentified_confirmed))
  form.append('expected_updated_at', payload.expected_updated_at)
  return mutateForm<CaseDraft>(
    `/api/teacher/cases/${caseId}/draft/physical-exam/assets/`,
    form,
  )
}

export function deletePhysicalExamAsset(
  caseId: string,
  assetId: number,
  expectedUpdatedAt: string,
): Promise<CaseDraft> {
  return mutate<CaseDraft>(
    'DELETE',
    `/api/teacher/cases/${caseId}/draft/physical-exam/assets/${assetId}/`,
    { expected_updated_at: expectedUpdatedAt },
  )
}

export function publishCase(caseId: string): Promise<{
  created: boolean
  version: { id: string; version_number: number; published_at: string; content_hash: string }
}> {
  return mutate('POST', `/api/teacher/cases/${caseId}/publish/`)
}

export async function listStudentAssignments(): Promise<StudentAssignment[]> {
  const response = await fetch('/api/student/assignments/', { credentials: 'same-origin' })
  return parseResponse<StudentAssignment[]>(response)
}

export function startStudentSession(
  assignmentId: string,
): Promise<{ created: boolean; session: SimulationSession }> {
  return mutate('POST', `/api/student/assignments/${assignmentId}/session/`)
}

export async function getStudentSession(sessionId: string): Promise<SimulationSession> {
  const response = await fetch(`/api/student/sessions/${sessionId}/`, {
    credentials: 'same-origin',
  })
  return parseResponse<SimulationSession>(response)
}

export function askPatient(
  sessionId: string,
  payload: { content: string; client_message_id: string },
): Promise<{
  student_message: SessionMessage
  patient_message: SessionMessage | null
  reused: boolean
  interaction_type: 'patient_answer' | 'physical_exam_released' | 'physical_exam_reopened' | 'patient_initiative_response'
}> {
  return mutate('POST', `/api/student/sessions/${sessionId}/messages/`, payload)
}

export function activatePatientInitiative(
  sessionId: string,
): Promise<{ patient_initiative: PatientInitiativeState }> {
  return mutate('POST', `/api/student/sessions/${sessionId}/patient-initiative/activate/`)
}

export function triggerPatientInitiative(
  sessionId: string,
): Promise<{
  patient_message: SessionMessage | null
  reused: boolean
  patient_initiative: PatientInitiativeState
}> {
  return mutate('POST', `/api/student/sessions/${sessionId}/patient-initiative/trigger/`)
}

export function saveStudentCaseDraft(
  sessionId: string,
  payload: { expected_revision: number; case_draft: StudentCaseDraft },
): Promise<{ case_draft: StudentCaseDraft; case_draft_revision: number }> {
  return mutate('PATCH', `/api/student/sessions/${sessionId}/draft/`, payload)
}

export function completeStudentSession(
  sessionId: string,
  payload: { expected_revision: number; case_record: StudentCaseDraft },
): Promise<{ reused: boolean; session: SimulationSession }> {
  return mutate('POST', `/api/student/sessions/${sessionId}/complete/`, payload)
}

export async function getSessionFeedback(sessionId: string): Promise<SessionFeedback> {
  const response = await fetch(`/api/student/sessions/${sessionId}/feedback/`, {
    credentials: 'same-origin',
  })
  return parseResponse<SessionFeedback>(response)
}

export async function listTeachingClasses(): Promise<TeachingClass[]> {
  const response = await fetch('/api/teacher/teaching/classes/', {
    credentials: 'same-origin',
  })
  return parseResponse<TeachingClass[]>(response)
}

export function createTeachingClass(payload: { name: string }): Promise<TeachingClass> {
  return mutate('POST', '/api/teacher/teaching/classes/', payload)
}

export function setTeachingClassActive(classId: string, isActive: boolean): Promise<void> {
  return mutate('PATCH', `/api/teacher/teaching/classes/${classId}/`, {
    is_active: isActive,
  })
}

export function removeClassStudent(classId: string, studentId: string): Promise<void> {
  return mutate('DELETE', `/api/teacher/teaching/classes/${classId}/students/${studentId}/`)
}

export function transferClassStudent(
  classId: string,
  studentId: string,
  targetClassId: string,
): Promise<void> {
  return mutate('PATCH', `/api/teacher/teaching/classes/${classId}/students/${studentId}/`, {
    target_class_id: targetClassId,
  })
}

export async function listManagedStudents(
  filters: ManagedStudentFilters = {},
): Promise<ManagedStudent[]> {
  const query = new URLSearchParams()
  if (filters.name) query.set('name', filters.name)
  if (filters.email) query.set('email', filters.email)
  if (filters.class_group_id) query.set('class_group_id', filters.class_group_id)
  const suffix = query.size > 0 ? `?${query.toString()}` : ''
  const response = await fetch(`/api/teacher/teaching/students/${suffix}`, {
    credentials: 'same-origin',
  })
  return parseResponse<ManagedStudent[]>(response)
}

export async function getManagedStudent(studentId: string): Promise<ManagedStudent> {
  const response = await fetch(`/api/teacher/teaching/students/${studentId}/`, {
    credentials: 'same-origin',
  })
  return parseResponse<ManagedStudent>(response)
}

export function updateManagedStudentClass(
  studentId: string,
  classGroupId: string,
): Promise<ManagedStudent> {
  return mutate('PATCH', `/api/teacher/teaching/students/${studentId}/`, {
    class_group_id: classGroupId,
  })
}

export async function listTeacherAssignments(): Promise<TeacherAssignment[]> {
  const response = await fetch('/api/teacher/assignments/', { credentials: 'same-origin' })
  return parseResponse<TeacherAssignment[]>(response)
}

export async function getAssignmentOptions(): Promise<AssignmentOptions> {
  const response = await fetch('/api/teacher/assignments/options/', {
    credentials: 'same-origin',
  })
  return parseResponse<AssignmentOptions>(response)
}

export function createTeacherAssignment(payload: {
  title: string
  case_version_id: string
  class_group_id: string
  duration_minutes: number
  opens_at: string
  deadline_at: string
}): Promise<TeacherAssignment> {
  return mutate('POST', '/api/teacher/assignments/', payload)
}

export function closeTeacherAssignment(assignmentId: string): Promise<TeacherAssignment> {
  return mutate('POST', `/api/teacher/assignments/${assignmentId}/close/`)
}

export function releaseTeacherAssignmentFeedback(
  assignmentId: string,
): Promise<TeacherAssignment> {
  return mutate('POST', `/api/teacher/assignments/${assignmentId}/release-feedback/`)
}

export async function listTeacherResponses(assignmentId: string): Promise<TeacherResponseRow[]> {
  const response = await fetch(`/api/teacher/assignments/${assignmentId}/responses/`, {
    credentials: 'same-origin',
  })
  return parseResponse<TeacherResponseRow[]>(response)
}

export async function getTeacherAssignmentStatistics(
  assignmentId: string,
): Promise<AssignmentStatistics> {
  const response = await fetch(`/api/teacher/assignments/${assignmentId}/statistics/`, {
    credentials: 'same-origin',
  })
  return parseResponse<AssignmentStatistics>(response)
}

export function teacherAssignmentCsvUrl(assignmentId: string): string {
  return `/api/teacher/assignments/${assignmentId}/export.csv`
}

export async function getTeacherSessionRecord(sessionId: string): Promise<TeacherSessionRecord> {
  const response = await fetch(`/api/teacher/sessions/${sessionId}/record/`, {
    credentials: 'same-origin',
  })
  return parseResponse<TeacherSessionRecord>(response)
}

export function saveTeacherReview(
  sessionId: string,
  payload: {
    comment: string
    scores: Array<{ code: string; score: number | null; reason: string }>
  },
): Promise<TeacherReview> {
  return mutate('POST', `/api/teacher/sessions/${sessionId}/reviews/`, payload)
}

export function runTeacherAIEvaluation(
  sessionId: string,
  force = false,
): Promise<AIEvaluationRun> {
  return mutate('POST', `/api/teacher/sessions/${sessionId}/ai-evaluation/`, { force })
}
