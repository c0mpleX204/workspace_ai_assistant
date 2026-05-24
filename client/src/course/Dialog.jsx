import React from 'react'
import {
  citationLabel,
  displayMessageContent,
  fileNameFromPath,
  formatMessageTime,
  formatTokenUsage,
} from '../shared/text'

function normalizePlan(message) {
  const direct = Array.isArray(message?.plan) ? message.plan : []
  const metadata = Array.isArray(message?.metadata?.plan) ? message.metadata.plan : []
  return direct.length ? direct : metadata
}

function AgentPlan({ plan }) {
  if (!plan || plan.length === 0) return null
  return (
    <div className="agent-plan">
      {plan.map(item => (
        <div className={`agent-plan-item ${item.status || 'pending'}`} key={item.id || item.title}>
          <span>{item.status === 'done' ? '✓' : item.status === 'running' ? '→' : '·'}</span>
          <b>{item.title}</b>
        </div>
      ))}
    </div>
  )
}

export function TypingIndicator() {
  return (
    <div className="msg-row assistant">
      <div className="msg-meta">AI</div>
      <div className="typing-indicator">
        <div className="typing-dot" /><div className="typing-dot" /><div className="typing-dot" />
      </div>
    </div>
  )
}

export function Message({ m, onCitationClick }) {
  const usageText = formatTokenUsage(m.usage || m.metadata?.usage)
  const timeText = formatMessageTime(m.created_at || m.createdAt)
  const plan = normalizePlan(m)
  const contentText = displayMessageContent(m.content)
  return (
    <div className={`msg-row ${m.role}`}>
      <div className="msg-meta">
        <span>{m.role === 'user' ? '你' : 'AI'}</span>
        {timeText && <time>{timeText}</time>}
      </div>
      <div className="msg-bubble">
        {m.attachments && m.attachments.length > 0 && (
          <div className="msg-attachments">
            {m.attachments.map(item => {
              const label = item.label || `${item.type === 'directory' ? '文件夹' : '文件'} · ${item.name || fileNameFromPath(item.path)}`
              return <span key={`${item.type}:${item.id || item.path || label}`}>{label}</span>
            })}
          </div>
        )}
        {m.images && m.images.length > 0 && (
          <div className="msg-images">{m.images.map((src, i) => <img key={i} className="msg-img" src={src} alt="" />)}</div>
        )}
        {contentText ? <span>{contentText}</span> : (m.streaming ? <span className="streaming-placeholder">正在生成...</span> : null)}
      </div>
      {m.role === 'assistant' && <AgentPlan plan={plan} />}
      {m.role === 'assistant' && m.refs && m.refs.length > 0 && (
        <div className="refs">
          {m.refs.map((ref, i) => (
            <button className="ref-item ref-clickable" key={i} onClick={() => onCitationClick?.(ref)} title="跳转到引用位置">
              <span className="ref-badge">{ref.ref_id}</span>
              <span>
                {citationLabel(ref)} - {ref.summary}
                {ref.source_path && <span className="ref-path" title={ref.source_path}>{ref.source_path}</span>}
              </span>
            </button>
          ))}
        </div>
      )}
      {m.role === 'assistant' && m.activity && m.activity.length > 0 && (
        <div className="agent-activity">
          {m.activity.map((item, idx) => (
            <div className={`agent-activity-item ${item.kind || 'activity'}`} key={`${idx}:${item.label}`}>
              <span>{item.label}</span>
              {item.detail && <code>{item.detail}</code>}
            </div>
          ))}
        </div>
      )}
      {m.role === 'assistant' && usageText && <div className="token-usage">{usageText}</div>}
    </div>
  )
}
