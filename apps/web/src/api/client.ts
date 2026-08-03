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
