import React from 'react'
import { formatMessageTime } from '../shared/text'

function Message({ m }) {
  const timeText = formatMessageTime(m.created_at || m.createdAt)
  return (
    <div className={`msg-row ${m.role}`}>
      <div className="msg-meta">
        <span>{m.role === 'user' ? '你' : 'AI'}</span>
        {timeText && <time>{timeText}</time>}
      </div>
      <div className="msg-bubble">
        {m.images?.length > 0 && (
          <div className="msg-images">
            {m.images.map((src, i) => (
              <img key={i} className="msg-img" src={src} alt="" />
            ))}
          </div>
        )}
        {m.content && <span>{m.content}</span>}
        {m.delegatedResult && (
          <div className="delegated-result-box">
            {m.delegatedResult.summary && (
              <div className="delegated-result-summary">{m.delegatedResult.summary}</div>
            )}
            {m.delegatedResult.raw && (
              <details className="delegated-result-raw">
                <summary>查看主模型原始输出</summary>
                <pre>{m.delegatedResult.raw}</pre>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function Typing() {
  return (
    <div className="msg-row assistant">
      <div className="msg-meta">AI</div>
      <div className="typing-indicator">
        <div className="typing-dot" />
        <div className="typing-dot" />
        <div className="typing-dot" />
      </div>
    </div>
  )
}

export default function CompanionView({
  onOpenLive2D,
  routeMode,
  setRouteMode,
  micEnabled,
  setMicEnabled,
  chatAreaRef,
  messages,
  visibleMessages,
  loading,
  composerRef,
  isDragging,
  setIsDragging,
  addImageFile,
  pendingImages,
  setPendingImages,
  textareaRef,
  input,
  setInput,
  handleSend,
  canSend,
  speechStatus,
  micLevel,
  logs,
}) {
  return (
    <div className="companion-layout">
      <div className="companion-left">
        <div className="companion-card companion-chat-card">
          <div className="companion-card-head">
            <div>
              <div className="companion-title">持续对话</div>
              <div className="companion-subtitle">实时语音识别 + 流式语音播报</div>
            </div>
            <div className="companion-head-controls">
              <button
                type="button"
                className="ghost-btn small companion-live2d-btn"
                onClick={() => onOpenLive2D?.()}
                title="弹出独立 Live2D 窗口"
              >
                Live2D
              </button>
              <select
                className="field-input field-select companion-route-select"
                value={routeMode}
                onChange={e => setRouteMode(e.target.value)}
                title="任务路由模式"
              >
                <option value="auto">自动分流</option>
                <option value="chat_only">仅聊天</option>
                <option value="task_auto">任务自动(Hard)</option>
                <option value="task_force_hard">强制Hard任务</option>
              </select>
              <label className="mic-switch">
                <input
                  type="checkbox"
                  checked={micEnabled}
                  onChange={e => setMicEnabled(e.target.checked)}
                />
                <span>{micEnabled ? 'Mic ON' : 'Mic OFF'}</span>
              </label>
            </div>
          </div>

          <div className="chat-area companion-chat-area" ref={chatAreaRef}>
            {messages.length === 0 && (
              <div className="chat-empty">
                <div className="chat-empty-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="22" height="22" strokeWidth="1.5"><rect x="9" y="2" width="6" height="11" rx="3" /><path d="M5 10a7 7 0 0 0 14 0" /><line x1="12" y1="18" x2="12" y2="22" /><line x1="9" y1="22" x2="15" y2="22" /></svg>
                </div>
                <p>打开麦克风即可持续语音对话</p>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>按 Y 键快速开关麦克风</span>
              </div>
            )}

            {visibleMessages.map((m, i) => (
              <Message key={i} m={m} />
            ))}

            {loading && !messages.some(m => m.streaming) && <Typing />}
          </div>

          <div
            className={`composer-wrap${isDragging ? ' drag-over' : ''}`}
            ref={composerRef}
            onDragOver={e => {
              e.preventDefault()
              setIsDragging(true)
            }}
            onDragLeave={e => {
              if (!composerRef.current?.contains(e.relatedTarget)) {
                setIsDragging(false)
              }
            }}
            onDrop={async e => {
              e.preventDefault()
              setIsDragging(false)
              for (const file of Array.from(e.dataTransfer.files).filter(file => file.type.startsWith('image/'))) {
                await addImageFile(file)
              }
            }}
          >
            {isDragging && (
              <div className="drop-overlay">
                <div className="drop-overlay-inner">
                  <span>松开放入图片</span>
                </div>
              </div>
            )}

            <div className="composer-box">
              {pendingImages.length > 0 && (
                <div className="composer-images">
                  {pendingImages.map((src, i) => (
                    <div key={i} className="composer-img-thumb">
                      <img src={src} alt="" />
                      <button
                        className="composer-img-remove"
                        onClick={() => setPendingImages(p => p.filter((_, j) => j !== i))}
                      >
                        x
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <textarea
                ref={textareaRef}
                className="composer-textarea"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSend()
                  }
                }}
                placeholder="输入文字或直接说话..."
                disabled={loading}
                rows={1}
              />

              <div className="composer-toolbar">
                <label className="composer-icon-btn" title="附加图片">
                  📷
                  <input
                    type="file"
                    accept="image/*"
                    style={{ display: 'none' }}
                    onChange={async e => {
                      if (e.target.files[0]) {
                        await addImageFile(e.target.files[0])
                        e.target.value = ''
                      }
                    }}
                  />
                </label>

                <div className="companion-meter-wrap">
                  <span className="companion-meter-label">{speechStatus}</span>
                  <div className="companion-meter">
                    <div
                      className="companion-meter-fill"
                      style={{ width: `${micLevel}%` }}
                    />
                  </div>
                </div>

                <div className="composer-spacer" />
                <button className="send-btn" onClick={handleSend} disabled={!canSend} title="发送">
                  ➤
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="companion-right companion-monitor-pane">
        <div className="companion-card monitor-card">
          <div className="monitor-title">后台检测日志</div>
          <div className="monitor-list">
            {logs.length === 0 && <div className="monitor-empty">暂无日志</div>}
            {logs.map((item, i) => (
              <div key={i} className={`monitor-item ${item.type}`}>
                <span className="monitor-time">[{item.ts}]</span>
                <span className="monitor-text">{item.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
