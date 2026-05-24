import React from 'react'
import { IconBook, IconChat, IconCompanion, IconLogo, IconSettings } from '../shared/icons'
import { createProjectChatThread, THREAD_DEFAULT_TITLE } from '../shared/threads'

export default function Workspace({
  width,
  userId,
  page,
  activeThreadId,
  sortedThreads,
  onNewThread,
  onOpenThread,
  courses,
  coursesLoading,
  projectThreads,
  activeCourse,
  activeProjectThreadId,
  sessionId,
  onCreateProject,
  onOpenProject,
  onNewProjectThread,
  onPage,
}) {
  return (
    <aside
      className="workspace-sidebar"
      style={{ width, minWidth: width, maxWidth: width }}
    >
      <div className="workspace-brand">
        <div className="workspace-logo"><IconLogo /></div>
        <div>
          <div className="workspace-title">Workspace</div>
          <div className="workspace-subtitle">{userId || 'user1'}</div>
        </div>
      </div>

      <button className="workspace-new-btn" onClick={onNewThread}>
        <span>+</span>
        <span>新对话</span>
      </button>

      <div className="workspace-scroll">
        <div className="workspace-section">
          <div className="workspace-section-title">无项目</div>
          <div className="workspace-thread-list">
            {sortedThreads.map(thread => (
              <button
                key={thread.id}
                className={`workspace-thread ${page === 'chat' && activeThreadId === thread.id ? 'active' : ''}`}
                onClick={() => onOpenThread(thread.id)}
                title={thread.title || THREAD_DEFAULT_TITLE}
              >
                <IconChat />
                <span>{thread.title || THREAD_DEFAULT_TITLE}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="workspace-section">
          <div className="workspace-section-head">
            <span className="workspace-section-title">项目</span>
            <button className="workspace-icon-btn" onClick={onCreateProject} title="新建项目">+</button>
          </div>
          {coursesLoading && <div className="workspace-empty">加载项目中...</div>}
          {!coursesLoading && courses.length === 0 && <div className="workspace-empty">暂无项目</div>}
          {courses.map(course => {
            const key = String(course.course_id)
            const threads = projectThreads[key] || []
            const isActiveProject = page === 'course_chat' && activeCourse?.course_id === course.course_id
            return (
              <div className={`workspace-project ${isActiveProject ? 'active' : ''}`} key={course.course_id}>
                <div className="workspace-project-row">
                  <button className="workspace-project-main" onClick={() => onOpenProject(course)} title={course.project_path || course.name}>
                    <IconBook />
                    <span>{course.name}</span>
                  </button>
                  <button className="workspace-icon-btn" onClick={() => onNewProjectThread(course)} title="新建项目对话">+</button>
                </div>
                <div className="workspace-thread-list project-thread-list">
                  {(threads.length ? threads : [createProjectChatThread(course.course_id, `course_${course.course_id}_${sessionId || 'default'}`)]).map(thread => (
                    <button
                      key={thread.id}
                      className={`workspace-thread nested ${isActiveProject && activeProjectThreadId === thread.id ? 'active' : ''}`}
                      onClick={() => onOpenProject(course, thread.id)}
                      title={thread.title || THREAD_DEFAULT_TITLE}
                    >
                      <IconChat />
                      <span>{thread.title || THREAD_DEFAULT_TITLE}</span>
                    </button>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="workspace-bottom">
        <button className={`workspace-nav-btn ${page === 'companion' ? 'active' : ''}`} onClick={() => onPage('companion')}>
          <IconCompanion />
          <span>陪伴聊天</span>
        </button>
        <button className={`workspace-nav-btn ${page === 'settings' ? 'active' : ''}`} onClick={() => onPage('settings')}>
          <IconSettings />
          <span>设置</span>
        </button>
      </div>
    </aside>
  )
}
