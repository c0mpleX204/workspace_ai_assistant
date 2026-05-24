import React from 'react'
import { IconTerminal } from '../shared/icons'

function TerminalTabs({ sessions, activeSession, onSelect }) {
  return (
    <div className="terminal-tabs">
      {sessions.map((session, idx) => (
        <button
          key={session.sessionId}
          type="button"
          className={`terminal-tab${session.sessionId === activeSession?.sessionId ? ' active' : ''}`}
          onClick={() => onSelect(session.sessionId)}
          title={session.cwd}
        >
          <span>{session.title || `终端 ${idx + 1}`}</span>
          {session.status === 'exited' && <em>已退出</em>}
        </button>
      ))}
    </div>
  )
}

export function TerminalWindow({
  activeTerminal,
  sessions,
  screenRef,
  onSelect,
  onNew,
  onClose,
}) {
  return (
    <div className="terminal-window-only">
      <div className="terminal-panel terminal-popout-panel" style={{ height: '100vh' }}>
        <div className="terminal-panel-head terminal-window-head">
          <div className="terminal-title">
            <IconTerminal />
            <span>PowerShell</span>
            <code title={activeTerminal?.cwd || ''}>{activeTerminal?.cwd || '终端窗口'}</code>
          </div>
          <div className="terminal-actions">
            <button type="button" className="ghost-btn small" onClick={onNew}>+</button>
            <button type="button" className="ghost-btn small" onClick={() => onClose(activeTerminal?.sessionId)}>结束</button>
          </div>
        </div>
        <TerminalTabs sessions={sessions} activeSession={activeTerminal} onSelect={onSelect} />
        <div
          className="terminal-screen"
          ref={screenRef}
          title="这是完整 PTY 终端，直接输入即可"
        />
      </div>
    </div>
  )
}

export function TerminalDock({
  activeCourse,
  activeTerminal,
  sessions,
  height,
  resizing,
  screenRef,
  onResizeStart,
  onDragTitle,
  onSelect,
  onNew,
  onPopout,
  onCollapse,
  onClose,
}) {
  return (
    <div className={`terminal-panel${resizing ? ' is-resizing' : ''}`} style={{ height }}>
      <div
        className="terminal-resize-handle"
        title="上下拖动调整终端高度"
        onMouseDown={onResizeStart}
      />
      <div
        className="terminal-panel-head"
        onMouseDown={onDragTitle}
        title="拖动标题栏可弹出为独立终端窗口"
      >
        <div className="terminal-title">
          <IconTerminal />
          <span>PowerShell</span>
          <code title={activeTerminal?.cwd || activeCourse.project_path || ''}>
            {activeTerminal?.cwd || activeCourse.project_path || '项目目录'}
          </code>
        </div>
        <div className="terminal-actions">
          <button type="button" className="ghost-btn small" onClick={onNew}>+</button>
          <button type="button" className="ghost-btn small" onClick={() => onPopout(activeTerminal?.sessionId)}>弹出</button>
          <button type="button" className="ghost-btn small" onClick={onCollapse}>收起</button>
          <button type="button" className="ghost-btn small" onClick={() => onClose(activeTerminal?.sessionId)}>结束</button>
        </div>
      </div>
      <TerminalTabs sessions={sessions} activeSession={activeTerminal} onSelect={onSelect} />
      <div
        className="terminal-screen"
        ref={screenRef}
        onDoubleClick={() => onPopout(activeTerminal?.sessionId)}
        title="这是完整 PTY 终端，直接输入即可；双击弹出窗口"
      />
    </div>
  )
}
