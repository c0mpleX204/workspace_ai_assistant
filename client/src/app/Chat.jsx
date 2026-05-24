import React from 'react'
import { IconChat, IconImage, IconMic } from '../shared/icons'
import { citationLabel, displayMessageContent, formatMessageTime, formatTokenUsage } from '../shared/text'

export function Message({ m, onImageClick, onTts }) {
  const usageText = formatTokenUsage(m.usage || m.metadata?.usage)
  const timeText = formatMessageTime(m.created_at || m.createdAt)
  const contentText = displayMessageContent(m.content)
  return (
    <div className={`msg-row ${m.role}`}>
      <div className="msg-meta">
        <span>{m.role === 'user' ? '你' : 'AI'}</span>
        {timeText && <time>{timeText}</time>}
        {m.role === 'assistant' && onTts && m.content && (
          <button
            className="tts-play-btn"
            title="朗读"
            onClick={() => onTts(m.content)}
            style={{ marginLeft: 6, background: 'none', border: 'none', cursor: 'pointer', opacity: 0.6, fontSize: 13, padding: '0 2px', color: 'inherit' }}
          >
            &#128266;
          </button>
        )}
      </div>
      <div className="msg-bubble">
        {m.images && m.images.length > 0 && (
          <div className="msg-images">
            {m.images.map((src, i) => (
              <img
                key={i}
                className="msg-img msg-img-clickable"
                src={src}
                alt=""
                title="点击查看大图"
                onClick={() => onImageClick?.(src)}
              />
            ))}
          </div>
        )}
        {contentText ? <span>{contentText}</span> : (m.streaming ? <span className="streaming-placeholder">正在生成...</span> : null)}
      </div>
      {m.role === 'assistant' && m.refs && m.refs.length > 0 && (
        <div className="refs">{m.refs.map((ref, i) => (
          <div className="ref-item" key={i}>
            <span className="ref-badge">{ref.ref_id}</span>
            <span>
              {citationLabel(ref)} - {ref.summary}
              {ref.source_path && <span className="ref-path" title={ref.source_path}>{ref.source_path}</span>}
            </span>
          </div>
        ))}</div>
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

export function Typing() {
  return (
    <div className="msg-row assistant">
      <div className="msg-meta">AI</div>
      <div className="typing-indicator"><div className="typing-dot" /><div className="typing-dot" /><div className="typing-dot" /></div>
    </div>
  )
}

export default function Chat({
  messages,
  loading,
  messagesEndRef,
  composerRef,
  textareaRef,
  input,
  setInput,
  pendingImages,
  setPendingImages,
  isDragging,
  setIsDragging,
  listening,
  onMic,
  onSend,
  onPaste,
  onAddImage,
  onImageClick,
  onTts,
  canSend,
}) {
  return (
    <>
      <div className="chat-area">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-icon"><IconChat /></div>
            <p>发送消息开始对话，支持图片和语音输入</p>
          </div>
        )}
        {messages.map((m, i) => <Message key={i} m={m} onImageClick={onImageClick} onTts={onTts} />)}
        {loading && !messages.some(m => m.streaming) && <Typing />}
        <div ref={messagesEndRef} />
      </div>
      <div
        className={`composer-wrap${isDragging ? ' drag-over' : ''}`}
        ref={composerRef}
        onDragOver={e => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={e => { if (!composerRef.current?.contains(e.relatedTarget)) setIsDragging(false) }}
        onDrop={async e => {
          e.preventDefault()
          setIsDragging(false)
          for (const file of Array.from(e.dataTransfer.files).filter(file => file.type.startsWith('image/'))) {
            await onAddImage(file)
          }
        }}
      >
        {isDragging && <div className="drop-overlay"><div className="drop-overlay-inner"><span>松开放入图片</span></div></div>}
        <div className="composer-box">
          {pendingImages.length > 0 && (
            <div className="composer-images">
              {pendingImages.map((src, i) => (
                <div key={i} className="composer-img-thumb">
                  <img src={src} alt="" />
                  <button className="composer-img-remove" onClick={() => setPendingImages(p => p.filter((_, j) => j !== i))}>x</button>
                </div>
              ))}
            </div>
          )}
          <textarea
            ref={textareaRef}
            className="composer-textarea"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend() } }}
            onPaste={onPaste}
            placeholder="发送消息... Enter 发送，Shift+Enter 换行，可粘贴/拖拽图片"
            disabled={loading}
            rows={1}
          />
          <div className="composer-toolbar">
            <label className="composer-icon-btn" title="附加图片">
              <IconImage />
              <input type="file" accept="image/*" style={{ display: 'none' }} onChange={async e => { if (e.target.files[0]) { await onAddImage(e.target.files[0]); e.target.value = '' } }} />
            </label>
            <button
              className={`composer-icon-btn mic-btn${listening ? ' mic-active' : ''}`}
              title={listening ? '点击停止录音' : '语音输入'}
              onClick={onMic}
            >
              <IconMic active={listening} />
            </button>
            <div className="composer-divider" />
            <div className="composer-spacer" />
            <button className="send-btn" onClick={onSend} disabled={!canSend} title="发送">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="14" height="14"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
