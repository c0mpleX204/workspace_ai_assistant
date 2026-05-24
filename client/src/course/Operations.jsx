import React from 'react'
import { formatMessageTime } from '../shared/text'

function normalizeOperations(message) {
  const direct = Array.isArray(message?.operations) ? message.operations : []
  const metadata = Array.isArray(message?.metadata?.operations) ? message.metadata.operations : []
  return direct.length ? direct : metadata
}

function OperationTextLines({ text, kind }) {
  const lines = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
  return (
    <div className={`agent-op-lines ${kind}`}>
      {lines.map((line, idx) => {
        const diffClass = kind === 'code'
          ? line.startsWith('+') ? ' add' : line.startsWith('-') ? ' del' : ''
          : ''
        return (
          <div className={`agent-op-line text${diffClass}`} key={idx}>
            <span className="agent-op-lineno">{idx + 1}</span>
            <span className="agent-op-text">{line || ' '}</span>
          </div>
        )
      })}
    </div>
  )
}

export default function OperationPanel({ messages }) {
  const operations = (messages || []).flatMap((message, messageIndex) =>
    normalizeOperations(message).map((operation, opIndex) => ({
      ...operation,
      _key: `${message.id || message.created_at || messageIndex}:${operation.id || opIndex}`,
    })),
  )
  return (
    <aside className="agent-ops-panel">
      <div className="agent-ops-head">
        <span>操作</span>
        <b>{operations.length}</b>
      </div>
      {operations.length === 0 ? (
        <div className="agent-ops-empty">终端指令、输出结果和代码片段会显示在这里</div>
      ) : (
        <div className="agent-ops-list">
          {operations.map(operation => (
            <div className={`agent-op-item ${operation.type || 'note'} ${operation.status || ''}`} key={operation._key}>
              <div className="agent-op-line agent-op-title">
                <span>{operation.type === 'terminal' || operation.type === 'terminal_interactive' ? 'terminal' : operation.type === 'code' ? 'code' : 'operation'}</span>
                {operation.created_at && <time>{formatMessageTime(operation.created_at)}</time>}
              </div>
              {operation.command && <div className="agent-op-line command"><span className="agent-op-prefix">$</span><code>{operation.command}</code></div>}
              {operation.cwd && <div className="agent-op-line path"><span className="agent-op-prefix">cwd</span><span>{operation.cwd}</span></div>}
              {operation.title && operation.type !== 'terminal' && <div className="agent-op-line label"><span>{operation.title}</span></div>}
              {operation.exit_code !== undefined && operation.exit_code !== null && (
                <div className="agent-op-line exit"><span className="agent-op-prefix">exit</span><span>{operation.exit_code}</span></div>
              )}
              {operation.stdout && <OperationTextLines text={operation.stdout} kind="stdout" />}
              {operation.stderr && <OperationTextLines text={operation.stderr} kind="stderr" />}
              {operation.code && <OperationTextLines text={operation.code} kind="code" />}
            </div>
          ))}
        </div>
      )}
    </aside>
  )
}
