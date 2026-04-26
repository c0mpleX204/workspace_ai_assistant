import React, { Suspense, lazy, useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { chatApi } from './api'
import CoursesPage from './CoursesPage'
import CourseChatPage from './CourseChatPage'
import './styles.css'

const CompanionChatPage = lazy(() => import('./CompanionChatPage'))

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = e => resolve(e.target.result)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

// ===== Icons =====
const IconChat = () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>)
const IconBook = () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>)
const IconSettings = () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>)
const IconCompanion = () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20a8 8 0 0 1 16 0"/></svg>)
const IconImage = () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>)
const IconLogo = () => (<svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2L2 7v10l10 5 10-5V7z"/><path d="M12 2v20"/><path d="M2 7l10 5 10-5"/></svg>)
const IconMic = ({ active }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" width="15" height="15" strokeLinecap="round" strokeLinejoin="round">
    <rect x="9" y="2" width="6" height="11" rx="3"/>
    <path d="M5 10a7 7 0 0 0 14 0"/>
    <line x1="12" y1="18" x2="12" y2="22"/>
    <line x1="9" y1="22" x2="15" y2="22"/>
    {active && <circle cx="20" cy="4" r="3" fill="#e5484d" stroke="none"/>}
  </svg>
)

// ===== Toast =====
function useToast() {
  const [toast, setToast] = useState({ msg: '', type: '', visible: false })
  const timerRef = useRef(null)
  const show = useCallback((msg, type = 'info') => {
    clearTimeout(timerRef.current)
    setToast({ msg, type, visible: true })
    timerRef.current = setTimeout(() => setToast(t => ({ ...t, visible: false })), 2800)
  }, [])
  return { toast, show }
}

// ===== 大图 Lightbox =====
function Lightbox({ src, onClose }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])
  if (!src) return null
  return (
    <div className="lightbox-overlay" onClick={onClose}>
      <img
        className="lightbox-img"
        src={src}
        alt="大图预览"
        onClick={e => e.stopPropagation()}
      />
      <button className="lightbox-close" onClick={onClose}>✕</button>
    </div>
  )
}

// ===== 语音输入 Hook（录音 + 后端 STT）=====
function useSpeechInput(backendUrl, selectedAudioInput) {
  const [listening, setListening] = useState(false)
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const streamRef = useRef(null)

  const startListening = useCallback(async (onResult, onError) => {
    try {
      const constraints = { audio: selectedAudioInput ? { deviceId: { exact: selectedAudioInput } } : true }
      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      streamRef.current = stream
      chunksRef.current = []
      const mr = new MediaRecorder(stream)
      mediaRecorderRef.current = mr
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        try {
          const form = new FormData()
          form.append('file', blob, 'audio.webm')
          const base = backendUrl || 'http://127.0.0.1:8000'
          const res = await fetch(base + '/stt', { method: 'POST', body: form })
          if (!res.ok) throw new Error(await res.text())
          const data = await res.json()
          onResult && onResult(data.text || '')
        } catch (err) {
          onError && onError('语音识别失败: ' + err.message)
        }
        setListening(false)
      }
      mr.start()
      setListening(true)
    } catch (err) {
      onError && onError('麦克风权限被拒绝或不可用: ' + err.message)
      setListening(false)
    }
  }, [backendUrl, selectedAudioInput])

  const stopListening = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    } else {
      streamRef.current?.getTracks().forEach(t => t.stop())
      setListening(false)
    }
  }, [])

  return { listening, startListening, stopListening }
}

// ===== 消息气泡 =====
function Message({ m, onImageClick, onTts }) {
  return (
    <div className={`msg-row ${m.role}`}>
      <div className="msg-meta">
        {m.role === 'user' ? '你' : 'AI'}
        {m.role === 'assistant' && onTts && m.content && (
          <button
            className="tts-play-btn"
            title="朗读"
            onClick={() => onTts(m.content)}
            style={{marginLeft:6,background:'none',border:'none',cursor:'pointer',opacity:0.6,fontSize:13,padding:'0 2px',color:'inherit'}}
          >&#128266;</button>
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
                onClick={() => onImageClick && onImageClick(src)}
              />
            ))}
          </div>
        )}
        {m.content && <span>{m.content}</span>}
      </div>
      {m.role === 'assistant' && m.refs && m.refs.length > 0 && (
        <div className="refs">{m.refs.map((r, i) => (
          <div className="ref-item" key={i}>
            <span className="ref-badge">{r.ref_id}</span>
            <span>{r.doucument_title}{r.page_no != null ? ` · p${r.page_no}` : ''} — {r.summary}</span>
          </div>
        ))}</div>
      )}
    </div>
  )
}
function TypingIndicator() {
  return (
    <div className="msg-row assistant">
      <div className="msg-meta">AI</div>
      <div className="typing-indicator"><div className="typing-dot"/><div className="typing-dot"/><div className="typing-dot"/></div>
    </div>
  )
}

const THREAD_KEY_PREFIX = 'desktop_chat_threads_v1:'
const THREAD_DEFAULT_TITLE = '新对话'

function buildChatThreadTitle(messages) {
  const firstUser = (messages || []).find(x => x?.role === 'user' && String(x?.content || '').trim())
  if (!firstUser) return THREAD_DEFAULT_TITLE
  const text = String(firstUser.content || '').trim().replace(/\s+/g, ' ')
  return text.slice(0, 18) || THREAD_DEFAULT_TITLE
}

function createChatThread(id = '') {
  const now = Date.now()
  return {
    id: id || `chat_${now}_${Math.random().toString(36).slice(2, 8)}`,
    title: THREAD_DEFAULT_TITLE,
    messages: [],
    createdAt: now,
    updatedAt: now,
  }
}

function normalizeChatThreads(raw) {
  if (!Array.isArray(raw)) return []
  const cleaned = raw
    .filter(x => x && typeof x.id === 'string' && x.id.trim())
    .map(x => {
      const msgs = Array.isArray(x.messages) ? x.messages : []
      return {
        id: String(x.id),
        title: String(x.title || '').trim() || buildChatThreadTitle(msgs),
        messages: msgs,
        createdAt: Number(x.createdAt || Date.now()),
        updatedAt: Number(x.updatedAt || Date.now()),
      }
    })
  return cleaned
}

// ===== 主应用 =====
export default function App() {
  const LIVE2D_BG_KEY = 'desktop_live2d_bg_url_v1'
  const [backendUrl, setBackendUrl] = useState(() => window.env?.BACKEND_URL || 'http://127.0.0.1:8000')
  const [userId, setUserId] = useState('user1')
  const [sessionId] = useState('default')
  const [chatThreads, setChatThreads] = useState(() => [createChatThread('chat_default')])
  const [activeThreadId, setActiveChatThreadId] = useState('chat_default')
  const [page, setPage] = useState('courses')
  const [activeCourse, setActiveCourse] = useState(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastLatency, setLastLatency] = useState(null)
  const [useRetrieval, setUseRetrieval] = useState(false)
  const [useWebSearch, setUseWebSearch] = useState(false)
  const [pendingImages, setPendingImages] = useState([])
  const [isDragging, setIsDragging] = useState(false)
  // 大图预览
  const [lightboxSrc, setLightboxSrc] = useState(null)
  // 音频设备
  const [audioInputs, setAudioInputs] = useState([])
  const [audioOutputs, setAudioOutputs] = useState([])
  const [selectedAudioInput, setSelectedAudioInput] = useState('')
  const [selectedAudioOutput, setSelectedAudioOutput] = useState('')
  // TTS 朗读开关
  const [ttsEnabled, setTtsEnabled] = useState(false)
  const [live2dBgUrl, setLive2dBgUrl] = useState(() => {
    try { return localStorage.getItem(LIVE2D_BG_KEY) || '' } catch { return '' }
  })
  const [isMaximized, setIsMaximized] = useState(false)

  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const composerRef = useRef(null)
  const { toast, show: showToast } = useToast()
  const { listening, startListening, stopListening } = useSpeechInput(backendUrl, selectedAudioInput)

  const threadStoreKey = useMemo(
    () => `${THREAD_KEY_PREFIX}${userId || 'user1'}`,
    [userId],
  )
  const activeThread = useMemo(
    () => chatThreads.find(x => x.id === activeThreadId) || chatThreads[0] || createChatThread('chat_default'),
    [chatThreads, activeThreadId],
  )
  const messages = activeThread?.messages || []
  const sortedThreads = useMemo(
    () => [...chatThreads].sort((a, b) => Number(b.updatedAt || 0) - Number(a.updatedAt || 0)),
    [chatThreads],
  )

  useEffect(() => {
    try {
      const raw = localStorage.getItem(threadStoreKey)
      const parsed = raw ? JSON.parse(raw) : []
      const normalized = normalizeChatThreads(parsed)
      if (normalized.length > 0) {
        setChatThreads(normalized)
        setActiveChatThreadId(normalized[0].id)
      } else {
        const first = createChatThread('chat_default')
        setChatThreads([first])
        setActiveChatThreadId(first.id)
      }
    } catch (e) {
      void e
      const first = createChatThread('chat_default')
      setChatThreads([first])
      setActiveChatThreadId(first.id)
    }
  }, [threadStoreKey])

  useEffect(() => {
    try {
      localStorage.setItem(threadStoreKey, JSON.stringify(chatThreads))
    } catch (e) {
      void e
    }
  }, [threadStoreKey, chatThreads])

  useEffect(() => {
    try {
      localStorage.setItem(LIVE2D_BG_KEY, String(live2dBgUrl || '').trim())
    } catch (e) {
      void e
    }
  }, [live2dBgUrl])

  const setMessages = useCallback((updater) => {
    setChatThreads(prev => prev.map(thread => {
      if (thread.id !== activeThreadId) return thread
      const current = Array.isArray(thread.messages) ? thread.messages : []
      const nextMessages = typeof updater === 'function' ? updater(current) : updater
      return {
        ...thread,
        messages: nextMessages,
        title: buildChatThreadTitle(nextMessages),
        updatedAt: Date.now(),
      }
    }))
  }, [activeThreadId])

  function newThread() {
    const thread = createChatThread()
    setChatThreads(prev => [thread, ...prev])
    setActiveChatThreadId(thread.id)
    setInput('')
    setPendingImages([])
    setLastLatency(null)
  }

  function clearThread() {
    setMessages(() => [])
    setLastLatency(null)
  }

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading, activeThreadId])
  useEffect(() => {
    const ta = textareaRef.current; if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
  }, [input])

  // 监听窗口最大化状态变化
  useEffect(() => {
    if (!window.windowApi) return
    window.windowApi.isMaximized().then(v => setIsMaximized(v))
    const unsub = window.windowApi.onStateChanged((isMax) => setIsMaximized(isMax))
    return () => { if (typeof unsub === 'function') unsub() }
  }, [])

  // 枚举音频设备（先请求麦克风权限，再枚举才有 label）
  useEffect(() => {
    const loadDevices = () => {
      navigator.mediaDevices?.enumerateDevices().then(devices => {
        setAudioInputs(devices.filter(d => d.kind === 'audioinput'))
        setAudioOutputs(devices.filter(d => d.kind === 'audiooutput'))
      }).catch(() => {})
    }
    loadDevices()
    navigator.mediaDevices?.addEventListener('devicechange', loadDevices)
    return () => navigator.mediaDevices?.removeEventListener('devicechange', loadDevices)
  }, [])

  // 请求麦克风权限（点设置页时触发，让设备列表有 label）
  function requestMicPermission() {
    navigator.mediaDevices?.getUserMedia({ audio: true })
      .then(stream => {
        stream.getTracks().forEach(t => t.stop())
        // 权限拿到后重新枚举
        navigator.mediaDevices.enumerateDevices().then(devices => {
          setAudioInputs(devices.filter(d => d.kind === 'audioinput'))
          setAudioOutputs(devices.filter(d => d.kind === 'audiooutput'))
        })
        showToast('已获取麦克风权限', 'success')
      })
      .catch(() => showToast('麦克风权限被拒绝', 'error'))
  }

  async function addImageFile(file) {
    if (!file || !file.type.startsWith('image/')) return
    try {
      const dataUrl = await fileToDataUrl(file)
      setPendingImages(p => [...p, dataUrl])
    } catch { showToast('图片读取失败', 'error') }
  }

  async function handleSend() {
    const text = input.trim()
    if (!text && pendingImages.length === 0) return
    const imgs = [...pendingImages]
    const userMsg = { role: 'user', content: text }
    setMessages(m => [...m, { ...userMsg, images: imgs }])
    setInput(''); setPendingImages([]); setLoading(true); setLastLatency(null)
    try {
      const payload = {
        user_id: userId,
        session_id: activeThreadId,
        messages: [userMsg],
        use_retrieval: useRetrieval,
        use_web_search: useWebSearch,
      }
      // 有图片时：把第一张 base64 作为 image_url 发给后端
      if (imgs.length > 0) payload.image_url = imgs[0]
      const resp = await chatApi(backendUrl, payload)
      const replyText = resp.reply || ''
      setMessages(m => [...m, { role: 'assistant', content: replyText, refs: resp.reference || [] }])
      if (resp.latency_ms) setLastLatency(resp.latency_ms)
      // TTS：调用后端接口朗读 AI 回复
      if (ttsEnabled && replyText) {
        try {
          const ttsRes = await fetch(backendUrl + '/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: replyText.slice(0, 500) })
          })
          if (!ttsRes.ok) {
            const errText = await ttsRes.text().catch(() => ttsRes.statusText)
            showToast('TTS 失败: ' + errText.slice(0, 60), 'error')
          } else {
            const audioBlob = await ttsRes.blob()
            const audioUrl = URL.createObjectURL(audioBlob)
            const audio = new Audio(audioUrl)
            if (selectedAudioOutput) {
              try { await audio.setSinkId(selectedAudioOutput) } catch(e) {
                showToast('输出设备切换失败，使用默认设备', 'error')
              }
            }
            audio.play().catch(e => showToast('音频播放失败: ' + e.message, 'error'))
            audio.onended = () => URL.revokeObjectURL(audioUrl)
          }
        } catch(e) { showToast('TTS 请求异常: ' + e.message, 'error') }
      }
    } catch (err) {
      setMessages(m => [...m, { role: 'assistant', content: '请求失败：' + (err?.message || err) }])
      showToast('请求失败', 'error')
    } finally { setLoading(false) }
  }

  async function handleTtsPlay(text) {
    if (!text) return
    try {
      const res = await fetch(backendUrl + '/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.slice(0, 500) })
      })
      if (!res.ok) { showToast('TTS 失败', 'error'); return }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      if (selectedAudioOutput) {
        try { await audio.setSinkId(selectedAudioOutput) } catch(e) {}
      }
      audio.play().catch(e => showToast('音频播放失败: ' + e.message, 'error'))
      audio.onended = () => URL.revokeObjectURL(url)
    } catch(e) { showToast('TTS 请求异常: ' + e.message, 'error') }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  async function handlePaste(e) {
    for (const item of e.clipboardData?.items || []) {
      if (item.type.startsWith('image/')) {
        const f = item.getAsFile(); if (f) { e.preventDefault(); await addImageFile(f) }
      }
    }
  }

  function handleMicClick() {
    if (listening) {
      stopListening()
    } else {
      startListening(
        (text) => {
          setInput(prev => prev ? prev + ' ' + text : text)
          showToast('识别完成', 'success')
        },
        (err) => showToast(err, 'error')
      )
    }
  }

  const canSend = (input.trim() || pendingImages.length > 0) && !loading

  const SidebarNav = () => (
    <div className="sidebar">
      <div className="sidebar-logo" title="校园学习助手"><IconLogo /></div>
      <button className={`sidebar-btn ${page==='courses'?'active':''}`} title="我的课程" onClick={() => setPage('courses')}><IconBook /></button>
      <button className={`sidebar-btn ${page==='chat'?'active':''}`} title="自由对话" onClick={() => setPage('chat')}><IconChat /></button>
      <button className={`sidebar-btn ${page==='companion'?'active':''}`} title="持续对话" onClick={() => setPage('companion')}><IconCompanion /></button>
      <div className="sidebar-spacer" />
      <button className={`sidebar-btn ${page==='settings'?'active':''}`} title="设置" onClick={() => setPage('settings')}><IconSettings /></button>
    </div>
  )

  if (page === 'course_chat' && activeCourse) {
    return (
      <div className="app">
        <SidebarNav />
        <div className="main" style={{overflow:'hidden'}}>
          <CourseChatPage course={activeCourse} backendUrl={backendUrl} userId={userId} sessionId={sessionId} showToast={showToast} onBack={() => setPage('courses')} />
        </div>
        <div className={`toast ${toast.type} ${toast.visible?'show':''}`}>{toast.msg}</div>
      </div>
    )
  }

  return (
    <div className="app">
      <Lightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />
      <SidebarNav />
      <div className="main">
        <div className="topbar">
          <span className="topbar-title">{page==='courses'?'我的课程':page==='chat'?'自由对话':page==='companion'?'持续对话':'设置'}</span>
          {page==='chat' && useRetrieval && <span className="topbar-tag">RAG</span>}
          {page==='chat' && useWebSearch && <span className="topbar-tag">联网</span>}
          <div className="topbar-spacer"/>
          {(page==='chat' || page==='companion') && (
            <span className={`topbar-status ${loading?'loading':''}`}>
              {loading ? '生成中…' : lastLatency ? `${lastLatency}ms` : '就绪'}
            </span>
          )}
          {window.windowApi && (
            <button
              title={isMaximized ? '还原窗口' : '最大化'}
              onClick={() => window.windowApi.maximizeToggle()}
              className="ghost-btn small"
              style={{WebkitAppRegion:'no-drag',padding:'3px 8px',fontSize:14}}
            >{isMaximized ? '⤡' : '□'}</button>
          )}
        </div>

        {page==='courses' && <CoursesPage backendUrl={backendUrl} userId={userId} showToast={showToast} onEnterCourse={c=>{setActiveCourse(c);setPage('course_chat')}} />}

        {page==='chat' && (
          <>
            <div className="chat-thread-bar">
              <select
                className="chat-thread-select"
                value={activeThreadId}
                onChange={e => setActiveChatThreadId(e.target.value)}
              >
                {sortedThreads.map(t => (
                  <option key={t.id} value={t.id}>
                    {t.title || THREAD_DEFAULT_TITLE}
                  </option>
                ))}
              </select>
              <button className="ghost-btn small" onClick={newThread}>+ 新对话</button>
              <button className="ghost-btn small" onClick={clearThread} disabled={messages.length === 0}>清空当前</button>
            </div>
            <div className="chat-area">
              {messages.length===0 && <div className="chat-empty"><div className="chat-empty-icon"><IconChat/></div><p>发送消息开始对话，支持图片和语音输入</p></div>}
              {messages.map((m,i)=><Message key={i} m={m} onImageClick={src => setLightboxSrc(src)} onTts={handleTtsPlay}/>)}
              {loading && <TypingIndicator/>}
              <div ref={messagesEndRef}/>
            </div>
            <div className={`composer-wrap${isDragging?' drag-over':''}`} ref={composerRef}
              onDragOver={e=>{e.preventDefault();setIsDragging(true)}}
              onDragLeave={e=>{if(!composerRef.current?.contains(e.relatedTarget))setIsDragging(false)}}
              onDrop={async e=>{e.preventDefault();setIsDragging(false);for(const f of Array.from(e.dataTransfer.files).filter(f=>f.type.startsWith('image/')))await addImageFile(f)}}
            >
              {isDragging && <div className="drop-overlay"><div className="drop-overlay-inner"><span>松开放入图片</span></div></div>}
              <div className="composer-box">
                {pendingImages.length > 0 && (
                  <div className="composer-images">
                    {pendingImages.map((src,i)=>(
                      <div key={i} className="composer-img-thumb">
                        <img src={src} alt=""/>
                        <button className="composer-img-remove" onClick={()=>setPendingImages(p=>p.filter((_,j)=>j!==i))}>x</button>
                      </div>
                    ))}
                  </div>
                )}
                <textarea ref={textareaRef} className="composer-textarea" value={input}
                  onChange={e=>setInput(e.target.value)} onKeyDown={handleKeyDown} onPaste={handlePaste}
                  placeholder="发送消息… Enter 发送，Shift+Enter 换行，可粘贴/拖拽图片" disabled={loading} rows={1}/>
                <div className="composer-toolbar">
                  <label className="composer-icon-btn" title="附加图片">
                    <IconImage/>
                    <input type="file" accept="image/*" style={{display:'none'}} onChange={async e=>{if(e.target.files[0]){await addImageFile(e.target.files[0]);e.target.value=''}}} />
                  </label>
                  <button
                    className={`composer-icon-btn mic-btn${listening?' mic-active':''}`}
                    title={listening ? '点击停止录音' : '语音输入'}
                    onClick={handleMicClick}
                  >
                    <IconMic active={listening} />
                  </button>
                  <div className="composer-divider"/>
                  <button className={`retrieval-toggle ${useRetrieval?'active':''}`} onClick={()=>setUseRetrieval(v=>!v)}>🔍 检索</button>
                  <button className={`retrieval-toggle ${useWebSearch?'active':''}`} onClick={()=>setUseWebSearch(v=>!v)} style={{marginLeft:4}}>🌐 联网</button>
                  <div className="composer-spacer"/>
                  <button className="send-btn" onClick={handleSend} disabled={!canSend} title="发送">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="14" height="14"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                  </button>
                </div>
              </div>
            </div>
          </>
        )}



        {page==='companion' && (
          <Suspense fallback={null}>
            <CompanionChatPage
              backendUrl={backendUrl}
              userId={userId}
              sessionId={sessionId}
              selectedAudioInput={selectedAudioInput}
              selectedAudioOutput={selectedAudioOutput}
              live2dBgUrl={live2dBgUrl}
              showToast={showToast}
            />
          </Suspense>
        )}
        {page==='settings' && (
          <div className="page-container">
            <div className="page-title">设置</div>

            <div className="settings-card">
              <div className="settings-card-title">服务连接</div>
              <div className="field-group">
                <div className="field">
                  <label className="field-label">后端地址</label>
                  <input className="field-input" value={backendUrl} onChange={e=>setBackendUrl(e.target.value)} placeholder="http://127.0.0.1:8000"/>
                </div>
                <div className="field">
                  <label className="field-label">用户 ID</label>
                  <input className="field-input" value={userId} onChange={e=>setUserId(e.target.value)} placeholder="user1"/>
                </div>
              </div>
            </div>

            <div className="settings-card">
              <div className="settings-card-title">显示</div>
              <div className="field-group">
                <div className="field">
                  <label className="field-label">Live2D 背景图 URL</label>
                  <div className="field-row">
                    <input
                      className="field-input"
                      value={live2dBgUrl}
                      onChange={e => setLive2dBgUrl(e.target.value)}
                      placeholder="https://... 或留空使用默认背景"
                    />
                    <button className="ghost-btn" onClick={() => setLive2dBgUrl('')} title="恢复默认背景">清空</button>
                  </div>
                </div>
              </div>
            </div>

            <div className="settings-card">
              <div className="settings-card-title">音频设备</div>
              <div className="field-group">
                <div className="field">
                  <label className="field-label">麦克风（输入）</label>
                  <div className="field-row">
                    <select className="field-input field-select" value={selectedAudioInput} onChange={e => setSelectedAudioInput(e.target.value)}>
                      <option value="">系统默认</option>
                      {audioInputs.map(d => (
                        <option key={d.deviceId} value={d.deviceId}>{d.label || `麦克风 ${d.deviceId.slice(0,8)}`}</option>
                      ))}
                    </select>
                    <button className="ghost-btn" onClick={requestMicPermission} title="授权后可显示设备名称">授权</button>
                  </div>
                </div>
                <div className="field">
                  <label className="field-label">扬声器（输出）</label>
                  <select className="field-input field-select" value={selectedAudioOutput} onChange={e => setSelectedAudioOutput(e.target.value)}>
                    <option value="">系统默认</option>
                    {audioOutputs.map(d => (
                      <option key={d.deviceId} value={d.deviceId}>{d.label || `扬声器 ${d.deviceId.slice(0,8)}`}</option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label className="field-label">AI 回复朗读（TTS）</label>
                  <button
                    className={`retrieval-toggle${ttsEnabled?' active':''}`}
                    onClick={() => setTtsEnabled(v => !v)}
                    style={{alignSelf:'flex-start'}}
                  >
                    {ttsEnabled ? '已开启' : '已关闭'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
      <div className={`toast ${toast.type} ${toast.visible?'show':''}`}>{toast.msg}</div>
    </div>
  )
}
    
