import { useState } from 'react'

import { TeacherAssignments } from './TeacherAssignments'
import { TeacherCases } from './TeacherCases'
import { TeachingGroups } from './TeachingGroups'

type WorkspaceTab = 'cases' | 'groups' | 'assignments'

export function TeacherWorkspace() {
  const [tab, setTab] = useState<WorkspaceTab>('cases')

  return (
    <div className="teacher-area">
      <nav className="teacher-tabs" aria-label="教师工作区">
        <button className={tab === 'cases' ? 'is-active' : ''} type="button" onClick={() => setTab('cases')}>病例库</button>
        <button className={tab === 'groups' ? 'is-active' : ''} type="button" onClick={() => setTab('groups')}>课程与学生</button>
        <button className={tab === 'assignments' ? 'is-active' : ''} type="button" onClick={() => setTab('assignments')}>考试任务</button>
      </nav>
      {tab === 'cases' && <TeacherCases />}
      {tab === 'groups' && <TeachingGroups />}
      {tab === 'assignments' && <TeacherAssignments />}
    </div>
  )
}
