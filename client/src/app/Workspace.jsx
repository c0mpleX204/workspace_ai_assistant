import React, { useRef, useState, useCallback } from 'react'
import { IconBook, IconChat, IconLogo, IconSettings } from '../shared/icons'
import { createProjectChatThread, THREAD_DEFAULT_TITLE } from '../shared/threads'

export default function Workspace({
  width,
  collapsed,
  page,
  activeThreadId,
  activePersonaId,
  sortedThreads,
  onNewThread,
  onOpenThread,
  onDeleteThread,
  onRenameThread,
  courses,
  coursesLoading,
  personas = [],
  personasLoading = false,
  onApplyPersona,
  onCreatePersona,
  onImportPersona,
  projectThreads,
  activeCourse,
  activeProjectThreadId,
  sessionId,
  onCreateProject,
  onOpenProject,
  onNewProjectThread,
  onDeleteProjectThread,
  onRenameProjectThread,
  onDeleteProject,
  onRenameProject,
  onPage,
  onToggleCollapse,
}) {
  const [contextMenu, setContextMenu] = useState(null)
  const [renamingId, setRenamingId] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const personaImportRef = useRef(null)

  const closeContextMenu = useCallback(() => setContextMenu(null), [])

  const handleThreadContext = (e, threadId) => {
    e.preventDefault()
    setContextMenu({ x: e.clientX, y: e.clientY, threadId, courseId: null, type: 'thread' })
  }

  const handleProjectThreadContext = (e, courseId, threadId) => {
    e.preventDefault()
    setContextMenu({ x: e.clientX, y: e.clientY, threadId, courseId, type: 'projectThread' })
  }

  const handleProjectContext = (e, courseId) => {
    e.preventDefault()
    setContextMenu({ x: e.clientX, y: e.clientY, threadId: null, courseId, type: 'project' })
  }

  const executeContextAction = (action) => {
    if (!contextMenu) return
    const { threadId, courseId, type } = contextMenu
    setContextMenu(null)

    if (action === 'rename') {
      let currentTitle = ''
      if (type === 'thread') {
        const t = sortedThreads.find(x => x.id === threadId)
        currentTitle = t?.title || ''
      } else if (type === 'projectThread') {
        const threads = projectThreads[String(courseId)] || []
        const t = threads.find(x => x.id === threadId)
        currentTitle = t?.title || ''
      }
      const newTitle = window.prompt('新名称:', currentTitle)
      if (newTitle && newTitle.trim() && newTitle.trim() !== currentTitle) {
        if (type === 'thread') {
          onRenameThread?.(threadId, newTitle.trim())
        } else if (type === 'projectThread') {
          onRenameProjectThread?.(courseId, threadId, newTitle.trim())
        }
      }
      return
    }

    if (action === 'renameProject') {
      const course = courses.find(c => String(c.course_id) === String(courseId))
      const newName = window.prompt('新项目名称:', course?.name || '')
      if (newName && newName.trim() && newName.trim() !== course?.name) {
        onRenameProject?.(courseId, newName.trim())
      }
      return
    }

    if (action === 'openInVSCode') {
      const course = courses.find(c => String(c.course_id) === String(courseId))
      const projectPath = course?.project_path
      if (projectPath && window.windowApi?.openInVSCode) {
        window.windowApi.openInVSCode(projectPath).catch(() => {})
      }
      return
    }

    if (action === 'openInTerminal') {
      const course = courses.find(c => String(c.course_id) === String(courseId))
      if (course) {
        onOpenProject(course)
        setTimeout(() => {
          if (window.windowApi?.openPowerShell) {
            window.windowApi.openPowerShell(course.project_path || '').catch(() => {})
          }
        }, 200)
      }
      return
    }

    if (action === 'deleteThread' && type === 'thread') {
      onDeleteThread?.(threadId)
    } else if (action === 'deleteThread' && type === 'projectThread') {
      onDeleteProjectThread?.(courseId, threadId)
    } else if (action === 'deleteProject' && type === 'project') {
      onDeleteProject?.(courseId)
    }
  }

  const findCourseByProjectThread = (threadId) => {
    for (const course of courses) {
      const key = String(course.course_id)
      const threads = projectThreads[key] || []
      if (threads.some(t => t.id === threadId)) return course
    }
    return null
  }

  const contextIsProjectThread = contextMenu?.type === 'projectThread'
  const contextCourse = contextIsProjectThread ? findCourseByProjectThread(contextMenu?.threadId) : null

  return (
    <aside
      className={`workspace-sidebar${collapsed ? ' collapsed' : ''}`}
      style={{ width, minWidth: width, maxWidth: width }}
    >
      <div className="workspace-brand">
        <div className="workspace-logo"><IconLogo /></div>
        <div>
          <div className="workspace-title">Workspace</div>
          <div className="workspace-subtitle">本地工作区</div>
        </div>
      </div>

      <button className="workspace-new-btn" onClick={onNewThread}>
        <span>+</span>
        <span>新对话</span>
      </button>
      <input
        ref={personaImportRef}
        type="file"
        accept=".md,text/markdown,text/plain"
        style={{ display: 'none' }}
        onChange={e => {
          const file = e.target.files?.[0]
          if (file) onImportPersona?.(file)
          e.target.value = ''
        }}
      />

      <div className="workspace-scroll">
        <div className="workspace-section">
          <div className="workspace-section-head">
            <span className="workspace-section-title">陪伴聊天</span>
            <div className="workspace-section-actions">
              <button className="workspace-icon-btn" onClick={onCreatePersona} title="新建人设 md">+</button>
              <button className="workspace-icon-btn" onClick={() => personaImportRef.current?.click()} title="导入人设 md">↑</button>
            </div>
          </div>
          <div className="workspace-thread-list">
            {personasLoading && <div className="workspace-empty">加载人设中...</div>}
            {!personasLoading && personas.length === 0 && <div className="workspace-empty">暂无人设 md</div>}
            {!personasLoading && personas.map(persona => (
              <button
                key={persona.id}
                className={`workspace-thread persona-thread ${activePersonaId === persona.id ? 'active' : ''}`}
                onClick={() => onApplyPersona?.(persona)}
                title={`用 ${persona.name} 处理当前对话`}
              >
                <IconChat />
                <span>{persona.name}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="workspace-section">
          <div className="workspace-section-title">无项目</div>
          <div className="workspace-thread-list">
            {sortedThreads.map(thread => (
              <button
                key={thread.id}
                className={`workspace-thread ${page === 'chat' && activeThreadId === thread.id ? 'active' : ''}`}
                onClick={() => onOpenThread(thread.id)}
                onContextMenu={(e) => handleThreadContext(e, thread.id)}
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
                  <button
                    className="workspace-project-main"
                    onClick={() => onOpenProject(course)}
                    onContextMenu={(e) => handleProjectContext(e, course.course_id)}
                    title={course.project_path || course.name}
                  >
                    <IconBook />
                    <span>{course.name}</span>
                  </button>
                  <button className="workspace-icon-btn" onClick={() => onNewProjectThread(course)} title="新建项目对话">+</button>
                </div>
                <div className="workspace-thread-list project-thread-list">
                  {(threads.length ? threads : [createProjectChatThread(course.course_id, `course_${course.course_id}_${sessionId || 'default'}`)]).map(thread => (
                    <button
                      key={thread.id}
                      className={`workspace-thread nested ${isActiveProject && activeProjectThreadId === thread.id ? 'active' : ''}${thread.type === 'pdf' ? ' pdf-thread' : ''}`}
                      onClick={() => onOpenProject(course, thread.id)}
                      onContextMenu={(e) => handleProjectThreadContext(e, course.course_id, thread.id)}
                      title={thread.title || THREAD_DEFAULT_TITLE}
                    >
                      {thread.type === 'pdf' ? (
                        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" width="14" height="14" strokeWidth="1.3"><path d="M4 1.5h5.5l4 4V13a.5.5 0 0 1-.5.5H4a.5.5 0 0 1-.5-.5V2a.5.5 0 0 1 .5-.5z"/><path d="M9.5 1.5V5.5h4"/><line x1="5.5" y1="8.5" x2="10.5" y2="8.5"/><line x1="5.5" y1="10.5" x2="9" y2="10.5"/></svg>
                      ) : (
                        <IconChat />
                      )}
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
        <button className={`workspace-nav-btn ${page === 'settings' ? 'active' : ''}`} onClick={() => onPage('settings')}>
          <IconSettings />
          <span>设置</span>
        </button>
      </div>

      {contextMenu && (
        <>
          <div className="context-menu-backdrop" onClick={closeContextMenu} onContextMenu={(e) => { e.preventDefault(); closeContextMenu() }} />
          <div className="context-menu" style={{ left: contextMenu.x, top: contextMenu.y }}>
            {contextMenu.type === 'project' ? (
              <>
                <button className="context-menu-item" onClick={() => executeContextAction('openInVSCode')}>在 VS Code 中打开</button>
                <button className="context-menu-item" onClick={() => executeContextAction('openInTerminal')}>在终端中打开</button>
                <div className="context-menu-divider" />
                <button className="context-menu-item" onClick={() => executeContextAction('renameProject')}>重命名</button>
                <div className="context-menu-divider" />
                <button className="context-menu-item danger" onClick={() => executeContextAction('deleteProject')}>删除项目</button>
              </>
            ) : (
              <>
                <button className="context-menu-item" onClick={() => executeContextAction('rename')}>重命名</button>
                <div className="context-menu-divider" />
                <button className="context-menu-item danger" onClick={() => executeContextAction('deleteThread')}>删除对话</button>
              </>
            )}
          </div>
        </>
      )}
    </aside>
  )
}
