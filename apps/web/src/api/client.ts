export type UserRole = 'student' | 'teacher' | 'administrator'

export type CurrentUser = {
  id: string
  phone: string
  display_name: string
  roles: UserRole[]
}

type AuthPayload = {
  phone: string
  password: string
  display_name?: string
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
  category: string
  standard_fact: string
  patient_expression: string
  semantic_tags: string[]
  synonyms: string[]
  disclosure_mode: string
  certainty: string
  unknown_response: string
  is_required: boolean
  score: string
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
  title_student: string
  specialty: string
  disease_tags: string[]
  difficulty: string
  estimated_minutes: number
  teaching_objectives: string
  target_grade: string
  is_exam_mode: boolean
  time_limit_minutes: number
  enabled_stages: string[]
  created_at: string
  updated_at: string
  patient_profile: PatientProfile
  facts: CaseFact[]
  tests: CaseTest[]
  diagnosis_rules: DiagnosisRule[]
  scoring_items: ScoringItem[]
}

export type CaseSummary = {
  id: string
  code: string
  is_active: boolean
  created_at: string
  draft: {
    id: string
    title_internal: string
    title_student: string
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
  case_title: string
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
  | 'initial_reasoning'
  | 'test_selection'
  | 'final_reasoning'
  | 'completed'

export type SessionMessage = {
  id: string
  sequence: number
  role: 'student' | 'patient' | 'system'
  content: string
  client_message_id: string
  reply_to_id: string | null
  response_status: 'processing' | 'completed' | 'failed' | 'not_applicable'
  error_code: string
  created_at: string
}

export type StageSubmission = {
  id: string
  submission_type: string
  payload: Record<string, unknown>
  submitted_at: string
}

export type SimulationSession = {
  id: string
  assignment_id: string
  assignment_title: string
  case_title: string
  patient_name: string
  opening_statement: string
  status: 'active' | 'completed' | 'expired'
  stage: SessionStage
  started_at: string
  deadline_at: string
  completed_at: string | null
  remaining_seconds: number
  messages: SessionMessage[]
  submissions: StageSubmission[]
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
  score: number | null
  ai_feedback: string
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly details?: unknown,
  ) {
    super(message)
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T

  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    let message = '请求失败，请稍后重试。'
    if (data && typeof data === 'object') {
      const values = Object.values(data)
      const first = values[0]
      if (typeof first === 'string') message = first
      if (Array.isArray(first) && typeof first[0] === 'string') message = first[0]
    }
    throw new ApiError(message, response.status, data)
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

async function mutate<T>(method: 'POST' | 'PATCH', path: string, payload?: unknown): Promise<T> {
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

export async function getCurrentUser(): Promise<CurrentUser> {
  const response = await fetch('/api/auth/me/', { credentials: 'same-origin' })
  return parseResponse<CurrentUser>(response)
}

export function register(payload: Required<AuthPayload>): Promise<CurrentUser> {
  return mutate<CurrentUser>('POST', '/api/auth/register/', payload)
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

export function createTeacherCase(payload: {
  code: string
  title_internal: string
  title_student: string
}): Promise<CaseDraft> {
  return mutate<CaseDraft>('POST', '/api/teacher/cases/', payload)
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
}> {
  return mutate('POST', `/api/student/sessions/${sessionId}/messages/`, payload)
}

export function submitSessionStage(
  sessionId: string,
  payload: { submission_type: string; payload: Record<string, unknown> },
): Promise<StageSubmission> {
  return mutate('POST', `/api/student/sessions/${sessionId}/submissions/`, payload)
}

export async function getSessionFeedback(sessionId: string): Promise<SessionFeedback> {
  const response = await fetch(`/api/student/sessions/${sessionId}/feedback/`, {
    credentials: 'same-origin',
  })
  return parseResponse<SessionFeedback>(response)
}
