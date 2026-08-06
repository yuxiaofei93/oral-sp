import { useState } from 'react'

import { ClassManagement } from './ClassManagement'
import { TeacherAssignments } from './TeacherAssignments'
import { TeacherCases } from './TeacherCases'

type WorkspaceTab = 'cases' | 'classes' | 'assignments'

export function TeacherWorkspace() {
  const [tab, setTab] = useState<WorkspaceTab>('cases')

  return (
    <div className="teacher-area">
      <nav className="teacher-tabs" aria-label="教师工作区">
        <button className={tab === 'cases' ? 'is-active' : ''} type="button" onClick={() => setTab('cases')}>病例库</button>
        <button className={tab === 'classes' ? 'is-active' : ''} type="button" onClick={() => setTab('classes')}>班级管理</button>
        <button className={tab === 'assignments' ? 'is-active' : ''} type="button" onClick={() => setTab('assignments')}>考试任务</button>
      </nav>
      {tab === 'cases' && <TeacherCases />}
      {tab === 'classes' && <ClassManagement />}
      {tab === 'assignments' && <TeacherAssignments />}
    </div>
  )
}
