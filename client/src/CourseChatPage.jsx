import React, { useState, useEffect, useRef } from 'react'
import { listMaterialsApi, uploadMaterialApi, chatApi, getMaterialViewUrl } from './api'

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = e => resolve(e.target.result)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function TypingIndicator() {
  return (
    <div className="msg-row assistant">
      <div className="msg-meta">AI</div>
      <div className="typing-indicator">
        <div className="typing-dot" /><div className="typing-dot" /><div className="typing-dot" />
      </div>
    </div>
  )
}

function Message({ m }) {
  return (
    <div className={`msg-row ${m.role}`}>
      <div className="msg-meta">{m.role === 'user' ? '你' : 'AI'}</div>
      <div className="msg-bubble">
        {m.images && m.images.length > 0 && (
          <div className="msg-images">{m.images.map((src, i) => <img key={i} className="msg-img" src={src} alt="" />)}</div>
        )}
        {m.content && <span>{m.content}</span>}
      </div>
      {m.role === 'assistant' && m.refs && m.refs.length > 0 && (
        <div className="refs">
          {m.refs.map((r, i) => (
            <div className="ref-item" key={i}>
              <span className="ref-badge">{r.ref_id}</span>
              <span>{r.doucument_title}{r.page_no != null ? ` · p${r.page_no}` : ''} — {r.summary}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function CourseChatPage({ course, backendUrl, userId, sessionId, showToast, onBack }) {
  const [materials, setMaterials] = useState([])
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [previewDocId, setPreviewDocId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastLatency, setLastLatency] = useState(null)
  const [useWebSearch, setUseWebSearch] = useState(false)
  const [pendingImages, setPendingImages] = useState([])
  const [isDragging, setIsDragging] = useState(false)
  const [uploadState, setUploadState] = useState({ title: '', file: null })
  const [uploadProgress, setUploadProgress] = useState(null)
  const [showUpload, setShowUpload] = useState(false)
  const [leftPaneWidth, setLeftPaneWidth] = useState(300)
  const [middlePaneWidth, setMiddlePaneWidth] = useState(540)
  const [resizing, setResizing] = useState(null)
  const [previewError, setPreviewError] = useState('')

  const layoutRef = useRef(null)
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const composerRef = useRef(null)

  useEffect(() => { fetchMaterials() }, [course.course_id])
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 180) + 'px'
  }, [input])

  useEffect(() => {
    if (!resizing) return
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'

    const onMove = (e) => {
      const root = layoutRef.current
      if (!root) return
      const rect = root.getBoundingClientRect()
      const x = e.clientX - rect.left

      if (resizing === 'left') {
        setLeftPaneWidth(Math.max(240, Math.min(460, x)))
      } else {
        const rightMin = 360
        const nextMiddleEnd = Math.max(leftPaneWidth + 360, Math.min(rect.width - rightMin, x))
        setMiddlePaneWidth(nextMiddleEnd - leftPaneWidth - 8)
      }
    }

    const onUp = () => {
      setResizing(null)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)

    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
  }, [resizing, leftPaneWidth])

  async function fetchMaterials() {
    try {
      const res = await listMaterialsApi(backendUrl, course.course_id)
      setMaterials(res.items || [])
      if (!previewDocId && res.items?.length) setPreviewDocId(res.items[0].document_id)
    } catch (e) {
      showToast('获取资料失败', 'error')
    }
  }

  function toggleSelect(docId) {
    setSelectedIds(prev => {
      const next = new Set(prev)
      next.has(docId) ? next.delete(docId) : next.add(docId)
      return next
    })
  }

  async function addImageFile(file) {
    if (!file || !file.type.startsWith('image/')) return
    try {
      const dataUrl = await fileToDataUrl(file)
      setPendingImages(p => [...p, dataUrl])
    } catch {
      showToast('图片读取失败', 'error')
    }
  }

  async function handleSend() {
    const text = input.trim()
    if (!text && pendingImages.length === 0) return

    const imgs = [...pendingImages]
    const userMsg = { role: 'user', content: text }
    setMessages(m => [...m, { ...userMsg, images: imgs }])
    setInput('')
    setPendingImages([])
    setLoading(true)
    setLastLatency(null)

    try {
      const docIds = Array.from(selectedIds)
      const payload = {
        user_id: userId,
        session_id: `course_${course.course_id}_${sessionId}`,
        messages: [userMsg],
        use_retrieval: docIds.length > 0,
        document_ids: docIds.length > 0 ? docIds : undefined,
        use_web_search: useWebSearch,
      }
      if (imgs.length > 0) payload.image_url = imgs[0]

      const resp = await chatApi(backendUrl, payload)
      setMessages(m => [...m, { role: 'assistant', content: resp.reply, refs: resp.reference || [] }])
      if (resp.latency_ms) setLastLatency(resp.latency_ms)
    } catch (err) {
      setMessages(m => [...m, { role: 'assistant', content: '请求失败：' + (err?.message || err) }])
      showToast('请求失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  async function handlePaste(e) {
    for (const item of e.clipboardData?.items || []) {
      if (item.type.startsWith('image/')) {
        const f = item.getAsFile()
        if (f) {
          e.preventDefault()
          await addImageFile(f)
        }
      }
    }
  }

  async function handleUpload(e) {
    e.preventDefault()
    if (!uploadState.file) { showToast('请选择文件', 'error'); return }
    if (!uploadState.title.trim()) { showToast('请填写标题', 'error'); return }

    const form = new FormData()
    form.append('course_id', course.course_id)
    form.append('title', uploadState.title)
    form.append('file', uploadState.file)

    setUploadProgress(0)
    try {
      const res = await uploadMaterialApi(backendUrl, form, p => setUploadProgress(p))
      showToast(`上传成功 · id=${res.document_id}`, 'success')
      setUploadState({ title: '', file: null })
      setUploadProgress(null)
      setShowUpload(false)
      fetchMaterials()
      setPreviewDocId(res.document_id)
    } catch (err) {
      setUploadProgress(null)
      showToast('上传失败：' + (err?.message || err), 'error')
    }
  }

  const canSend = (input.trim() || pendingImages.length > 0) && !loading
  const useRetrieval = selectedIds.size > 0

  return (
    <div className={`course-chat-layout${resizing ? " is-resizing" : ""}`} ref={layoutRef}>
      <div className="course-sidebar" style={{ width: leftPaneWidth, minWidth: leftPaneWidth, maxWidth: leftPaneWidth }}>
        <div className="course-sidebar-header">
          <button className="back-btn" onClick={onBack}>← 返回</button>
          <div className="course-sidebar-name">{course.name}</div>
          <button className="ghost-btn small" onClick={() => setShowUpload(v => !v)}>+ 上传</button>
        </div>

        {showUpload && (
          <form className="sidebar-upload-form" onSubmit={handleUpload}>
            <input className="field-input" placeholder="资料标题" value={uploadState.title}
              onChange={e => setUploadState(s => ({ ...s, title: e.target.value }))} />
            <label className="file-label small">
              {uploadState.file ? uploadState.file.name : '选择 PDF / TXT'}
              <input type="file" accept=".pdf,.txt" style={{ display: 'none' }}
                onChange={e => setUploadState(s => ({ ...s, file: e.target.files[0] }))} />
            </label>
            {uploadProgress !== null && (
              <div className="progress-bar"><div className="progress-fill" style={{ width: uploadProgress + '%' }} /></div>
            )}
            <button className="upload-btn small" type="submit" disabled={uploadProgress !== null}>
              {uploadProgress !== null ? `${uploadProgress}%` : '上传'}
            </button>
          </form>
        )}

        <div className="sidebar-section-label">资料列表（勾选参与对话）</div>
        <div className="sidebar-mat-list">
          {materials.length === 0 && <div className="sidebar-empty">暂无资料</div>}
          {materials.map(mat => (
            <div key={mat.document_id}
              className={`sidebar-mat-item ${selectedIds.has(mat.document_id) ? 'selected' : ''} ${previewDocId === mat.document_id ? 'previewing' : ''}`}
            >
              <input type="checkbox" checked={selectedIds.has(mat.document_id)}
                onChange={() => toggleSelect(mat.document_id)}
                onClick={e => e.stopPropagation()} />
              <div className="sidebar-mat-info"
                onClick={() => setPreviewDocId(mat.document_id)}>
                <div className="sidebar-mat-title">{mat.title}</div>
                <div className="sidebar-mat-meta">{mat.file_type.toUpperCase()} · {mat.chunk_count} chunks</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="pane-resizer" onMouseDown={(e) => { e.preventDefault(); setResizing('left') }} />

      <div className="course-chat-middle" style={{ width: middlePaneWidth, minWidth: middlePaneWidth, maxWidth: middlePaneWidth }}>
        <div className="preview-topbar">
          <span>文件预览</span>
          {previewDocId && <button className="ghost-btn small" onClick={() => setPreviewDocId(null)}>关闭预览</button>}
        </div>
        {previewDocId ? (
          <iframe className="preview-iframe" src={`${getMaterialViewUrl(backendUrl, previewDocId)}?inline=1`} title="preview" />
        ) : (
          <div className="preview-empty">
            <div style={{textAlign:'center'}}>
              <div style={{fontSize:32,marginBottom:12,opacity:0.3}}>📄</div>
              <div>点击左侧资料名称开始预览</div>
            </div>
          </div>
        )}
      </div>

      <div className="pane-resizer" onMouseDown={(e) => { e.preventDefault(); setResizing('middle') }} />

      <div className="course-chat-right">
        <div className="chat-panel">
          <div className="topbar">
            <span className="topbar-title">{useRetrieval ? `已选 ${selectedIds.size} 份资料` : '自由对话'}</span>
            <button className={`retrieval-toggle ${useWebSearch ? 'active' : ''}`}
              onClick={() => setUseWebSearch(v => !v)} title="联网搜索">🌐 联网</button>
            <div className="topbar-spacer" />
            <span className={`topbar-status ${loading ? 'loading' : ''}`}>
              {loading ? '生成中…' : lastLatency ? `${lastLatency} ms` : 'ready'}
            </span>
          </div>

          <div className="chat-area">
            {messages.length === 0 && (
              <div className="chat-empty">
                <div className="chat-empty-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="22" height="22" strokeWidth="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                </div>
                <p>{useRetrieval ? `基于 ${selectedIds.size} 份资料对话` : '勾选左侧资料开启 RAG，或直接发消息'}</p>
              </div>
            )}
            {messages.map((m, i) => <Message key={i} m={m} />)}
            {loading && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </div>

          <div className={`composer-wrap${isDragging ? ' drag-over' : ''}`} ref={composerRef}
            onDragOver={e => { e.preventDefault(); setIsDragging(true) }}
            onDragLeave={e => { if (!composerRef.current?.contains(e.relatedTarget)) setIsDragging(false) }}
            onDrop={async e => {
              e.preventDefault(); setIsDragging(false)
              for (const f of Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'))) await addImageFile(f)
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
              <textarea ref={textareaRef} className="composer-textarea" value={input}
                onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown} onPaste={handlePaste}
                placeholder="发消息… Enter发送，Shift+Enter换行，可粘贴/拖拽图片" disabled={loading} rows={1} />
              <div className="composer-toolbar">
                <label className="composer-icon-btn" title="附加图片">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="15" height="15"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" /></svg>
                  <input type="file" accept="image/*" style={{ display: 'none' }} onChange={async e => {
                    if (e.target.files[0]) { await addImageFile(e.target.files[0]); e.target.value = '' }
                  }} />
                </label>
                <div className="composer-spacer" />
                <button className="send-btn" onClick={handleSend} disabled={!canSend} title="发送">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="14" height="14"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
