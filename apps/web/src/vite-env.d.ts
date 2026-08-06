/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PORTAL?: 'student' | 'teacher'
  readonly VITE_STUDENT_ORIGIN?: string
  readonly VITE_TEACHER_ORIGIN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
