import React, { Suspense, lazy, useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Terminal as XTerm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { chatApi, getProviderSettingsApi, updateProviderSettingsApi, getChatSessionApi, listCoursesApi, createCourseApi } from './api'
import CourseChatPage from './CourseChatPage'
import '@xterm/xterm/css/xterm.css'
import './styles.css'

const CompanionChatPage = lazy(() => import('./CompanionChatPage'))
const APP_SEARCH_PARAMS = new URLSearchParams(window.location.search)
const IS_TERMINAL_WINDOW = APP_SEARCH_PARAMS.get('terminalWindow') === '1'
const INITIAL_TERMINAL_SESSION_ID = APP_SEARCH_PARAMS.get('sessionId') || ''

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
const IconTerminal = () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>)
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
            <span>
              {r.doucument_title}{r.page_no != null ? ` · p${r.page_no}` : ''} — {r.summary}
              {r.source_path && <span className="ref-path" title={r.source_path}>{r.source_path}</span>}
            </span>
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
const PROJECT_THREAD_KEY_PREFIX = 'project_chat_threads_v1:'
const THREAD_DEFAULT_TITLE = '新对话'
const MASKED_KEY_VALUE = '••••••••'
const PROVIDER_API_PLACEHOLDER = 'https://api.deepseek.com'
const DEFAULT_PROVIDER_SETTINGS = {
  api_base_url: '',
  api_key_masked: '',
  has_api_key: false,
  fast_model: '',
  heavy_model: '',
}

function buildChatThreadTitle(messages) {
  const firstUser = (messages || []).find(x => x?.role === 'user' && String(x?.content || '').trim())
  if (!firstUser) return THREAD_DEFAULT_TITLE
  const text = String(firstUser.content || '').trim().replace(/\s+/g, ' ')
  return text.slice(0, 18) || THREAD_DEFAULT_TITLE
}

function normalizeThreadTitle(value, fallback = THREAD_DEFAULT_TITLE) {
  const text = String(value || '').trim()
  if (!text || text === 'New chat') return fallback
  return text
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

function createProjectChatThread(courseId, id = '') {
  const now = Date.now()
  return {
    id: id || `course_${courseId}_${now}_${Math.random().toString(36).slice(2, 8)}`,
    title: THREAD_DEFAULT_TITLE,
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
        title: normalizeThreadTitle(x.title, buildChatThreadTitle(msgs)),
        messages: msgs,
        createdAt: Number(x.createdAt || Date.now()),
        updatedAt: Number(x.updatedAt || Date.now()),
      }
    })
  return cleaned
}

function normalizeProjectThreads(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const result = {}
  for (const [courseId, items] of Object.entries(raw)) {
    if (!Array.isArray(items)) continue
    const cleaned = items
      .filter(x => x && typeof x.id === 'string' && x.id.trim())
      .map(x => ({
        id: String(x.id),
        title: normalizeThreadTitle(x.title),
        createdAt: Number(x.createdAt || Date.now()),
        updatedAt: Number(x.updatedAt || Date.now()),
      }))
    if (cleaned.length > 0) result[String(courseId)] = cleaned
  }
  return result
}

// ===== 主应用 =====
export default function App() {
  const LIVE2D_BG_KEY = 'desktop_live2d_bg_url_v1'
  const [backendUrl, setBackendUrl] = useState(() => window.env?.BACKEND_URL || 'http://127.0.0.1:8000')
  const [userId, setUserId] = useState('user1')
  const [providerSettings, setProviderSettings] = useState(DEFAULT_PROVIDER_SETTINGS)
  const [providerDraft, setProviderDraft] = useState({
    api_base_url: '',
    api_key: '',
  })
  const [savingProvider, setSavingProvider] = useState(false)
  const [sessionId] = useState('default')
  const [chatThreads, setChatThreads] = useState(() => [createChatThread('chat_default')])
  const [activeThreadId, setActiveChatThreadId] = useState('chat_default')
  const [courses, setCourses] = useState([])
  const [coursesLoading, setCoursesLoading] = useState(false)
  const [projectThreads, setProjectThreads] = useState({})
  const [projectThreadsLoaded, setProjectThreadsLoaded] = useState(false)
  const [activeProjectThreadId, setActiveProjectThreadId] = useState('')
  const [page, setPage] = useState('chat')
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
  const [terminalOpen, setTerminalOpen] = useState(false)
  const [terminalSessions, setTerminalSessions] = useState([])
  const [activeTerminalId, setActiveTerminalId] = useState('')
  const [terminalHeight, setTerminalHeight] = useState(320)
  const [terminalResizing, setTerminalResizing] = useState(false)

  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const composerRef = useRef(null)
  const terminalContainerRef = useRef(null)
  const terminalResizeStartRef = useRef(null)
  const xtermRef = useRef(null)
  const fitAddonRef = useRef(null)
  const xtermSessionIdRef = useRef('')
  const terminalBuffersRef = useRef(new Map())
  const { toast, show: showToast } = useToast()
  const { listening, startListening, stopListening } = useSpeechInput(backendUrl, selectedAudioInput)

  const threadStoreKey = useMemo(
    () => `${THREAD_KEY_PREFIX}${userId || 'user1'}`,
    [userId],
  )
  const projectThreadStoreKey = useMemo(
    () => `${PROJECT_THREAD_KEY_PREFIX}${userId || 'user1'}`,
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
  const activeCourseId = activeCourse ? String(activeCourse.course_id) : ''
  const activeProjectThreads = activeCourseId ? (projectThreads[activeCourseId] || []) : []
  const sortedProjectThreads = useMemo(
    () => [...activeProjectThreads].sort((a, b) => Number(b.updatedAt || 0) - Number(a.updatedAt || 0)),
    [activeProjectThreads],
  )
  const activeProjectThread = useMemo(
    () => activeProjectThreads.find(x => x.id === activeProjectThreadId) || activeProjectThreads[0] || null,
    [activeProjectThreads, activeProjectThreadId],
  )
  const activeTerminal = useMemo(
    () => terminalSessions.find(x => x.sessionId === activeTerminalId) || terminalSessions[0] || null,
    [terminalSessions, activeTerminalId],
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
    setProjectThreadsLoaded(false)
    try {
      const raw = localStorage.getItem(projectThreadStoreKey)
      const parsed = raw ? JSON.parse(raw) : {}
      setProjectThreads(normalizeProjectThreads(parsed))
      setProjectThreadsLoaded(true)
    } catch (e) {
      void e
      setProjectThreads({})
      setProjectThreadsLoaded(true)
    }
  }, [projectThreadStoreKey])

  useEffect(() => {
    if (!projectThreadsLoaded) return
    try {
      localStorage.setItem(projectThreadStoreKey, JSON.stringify(projectThreads))
    } catch (e) {
      void e
    }
  }, [projectThreadStoreKey, projectThreads, projectThreadsLoaded])

  useEffect(() => {
    let cancelled = false

    async function loadCourses() {
      setCoursesLoading(true)
      try {
        const res = await listCoursesApi(backendUrl, userId)
        if (cancelled) return
        const items = res.items || []
        setCourses(items)
        setProjectThreads(prev => {
          const next = { ...prev }
          for (const course of items) {
            const key = String(course.course_id)
            if (!Array.isArray(next[key]) || next[key].length === 0) {
              next[key] = [createProjectChatThread(course.course_id, `course_${course.course_id}_${sessionId || 'default'}`)]
            }
          }
          return next
        })
      } catch (e) {
        if (!cancelled) showToast('获取项目失败: ' + (e?.message || e), 'error')
      } finally {
        if (!cancelled) setCoursesLoading(false)
      }
    }

    loadCourses()
    return () => { cancelled = true }
  }, [backendUrl, userId, sessionId, showToast])

  useEffect(() => {
    if (page !== 'chat' || !activeThreadId || messages.length > 0) return
    let cancelled = false

    async function loadThreadHistory() {
      try {
        const res = await getChatSessionApi(backendUrl, activeThreadId, userId)
        if (cancelled) return
        const stored = Array.isArray(res.messages) ? res.messages : []
        if (stored.length === 0) return
        setChatThreads(prev => prev.map(thread => {
          if (thread.id !== activeThreadId) return thread
          const current = Array.isArray(thread.messages) ? thread.messages : []
          if (current.length > 0) return thread
          return {
            ...thread,
            messages: stored.filter(m => m?.role === 'user' || m?.role === 'assistant'),
            title: res.title || thread.title || THREAD_DEFAULT_TITLE,
            updatedAt: res.updated_at ? Date.parse(res.updated_at) || Date.now() : Date.now(),
          }
        }))
      } catch (e) {
        void e
      }
    }

    loadThreadHistory()
    return () => { cancelled = true }
  }, [backendUrl, userId, activeThreadId, page, messages.length])

  useEffect(() => {
    try {
      localStorage.setItem(LIVE2D_BG_KEY, String(live2dBgUrl || '').trim())
    } catch (e) {
      void e
    }
  }, [live2dBgUrl])

  const loadProviderSettings = useCallback(async (showErrors = false) => {
    try {
      const res = await getProviderSettingsApi(backendUrl)
      const provider = { ...DEFAULT_PROVIDER_SETTINGS, ...(res.provider || {}) }
      setProviderSettings(provider)
      setProviderDraft({
        api_base_url: provider.api_base_url || '',
        api_key: provider.has_api_key ? MASKED_KEY_VALUE : '',
      })
    } catch (e) {
      if (showErrors) showToast('模型 API 设置读取失败: ' + (e?.message || e), 'error')
    }
  }, [backendUrl, showToast])

  useEffect(() => {
    loadProviderSettings(false)
  }, [loadProviderSettings])

  async function saveProviderSettings() {
    setSavingProvider(true)
    try {
      const payload = {
        api_base_url: String(providerDraft.api_base_url || '').trim(),
      }
      const keyText = String(providerDraft.api_key || '')
      if (keyText !== MASKED_KEY_VALUE) {
        payload.api_key = keyText.trim()
      }
      const res = await updateProviderSettingsApi(backendUrl, payload)
      const provider = { ...DEFAULT_PROVIDER_SETTINGS, ...(res.provider || {}) }
      setProviderSettings(provider)
      setProviderDraft({
        api_base_url: provider.api_base_url || '',
        api_key: provider.has_api_key ? MASKED_KEY_VALUE : '',
      })
      showToast('模型 API 设置已保存', 'success')
    } catch (e) {
      showToast('模型 API 设置保存失败: ' + (e?.message || e), 'error')
    } finally {
      setSavingProvider(false)
    }
  }

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
    setActiveCourse(null)
    setPage('chat')
    setInput('')
    setPendingImages([])
    setLastLatency(null)
  }

  function openThread(threadId) {
    setActiveChatThreadId(threadId)
    setActiveCourse(null)
    setPage('chat')
    setInput('')
    setPendingImages([])
    setLastLatency(null)
  }

  function openProject(course, threadId = '') {
    const key = String(course.course_id)
    const existing = projectThreads[key] || []
    const thread = existing.find(x => x.id === threadId) || existing[0] || createProjectChatThread(course.course_id, `course_${course.course_id}_${sessionId || 'default'}`)
    if (existing.length === 0) {
      setProjectThreads(prev => ({ ...prev, [key]: [thread] }))
    }
    setActiveCourse(course)
    setActiveProjectThreadId(thread.id)
    setPage('course_chat')
    setInput('')
    setPendingImages([])
    setLastLatency(null)
  }

  function newProjectThread(course) {
    const key = String(course.course_id)
    const thread = createProjectChatThread(course.course_id)
    setProjectThreads(prev => ({ ...prev, [key]: [thread, ...(prev[key] || [])] }))
    setActiveCourse(course)
    setActiveProjectThreadId(thread.id)
    setPage('course_chat')
    setInput('')
    setPendingImages([])
    setLastLatency(null)
  }

  async function createProjectFromSidebar() {
    const name = window.prompt('新项目名称')
    if (!name || !name.trim()) return
    try {
      const created = await createCourseApi(backendUrl, {
        name: name.trim(),
        term: null,
        owner_id: userId,
      })
      const course = created || {}
      const normalized = {
        ...course,
        course_id: course.course_id,
        name: course.name || name.trim(),
        doc_count: course.doc_count || 0,
      }
      setCourses(prev => [normalized, ...prev])
      const thread = createProjectChatThread(normalized.course_id, `course_${normalized.course_id}_${sessionId || 'default'}`)
      setProjectThreads(prev => ({ ...prev, [String(normalized.course_id)]: [thread] }))
      setActiveCourse(normalized)
      setActiveProjectThreadId(thread.id)
      setPage('course_chat')
      setInput('')
      setPendingImages([])
      setLastLatency(null)
      showToast('项目已创建', 'success')
    } catch (e) {
      showToast('创建项目失败: ' + (e?.message || e), 'error')
    }
  }

  function updateProjectThreadTitle(courseId, threadId, title) {
    const text = String(title || '').trim()
    if (!courseId || !threadId || !text || text === 'New chat') return
    const key = String(courseId)
    setProjectThreads(prev => ({
      ...prev,
      [key]: (prev[key] || []).map(thread => (
        thread.id === threadId
          ? { ...thread, title: text, updatedAt: Date.now() }
          : thread
      )),
    }))
  }

  function clearThread() {
    setMessages(() => [])
    setLastLatency(null)
  }

  function upsertTerminalSession(session) {
    if (!session?.sessionId) return
    if (typeof session.buffer === 'string') {
      terminalBuffersRef.current.set(session.sessionId, session.buffer)
    }
    setTerminalSessions(prev => {
      const idx = prev.findIndex(x => x.sessionId === session.sessionId)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = { ...next[idx], ...session }
        return next
      }
      return [...prev, session]
    })
    setActiveTerminalId(session.sessionId)
  }

  function appendTerminalOutput(sessionId, text) {
    const chunk = String(text || '')
    const sid = String(sessionId || '')
    if (!chunk || !sid) return
    const nextBuffer = String((terminalBuffersRef.current.get(sid) || '') + chunk).slice(-200000)
    terminalBuffersRef.current.set(sid, nextBuffer)
    setTerminalSessions(prev => {
      if (prev.some(session => session.sessionId === sid)) return prev
      return [...prev, { sessionId: sid, cwd: '', title: 'PowerShell', status: 'running', buffer: nextBuffer }]
    })
  }

  function fitActiveTerminal() {
    const term = xtermRef.current
    const fitAddon = fitAddonRef.current
    const sessionId = xtermSessionIdRef.current
    if (!term || !fitAddon || !sessionId) return
    try {
      fitAddon.fit()
      window.windowApi?.resizeTerminal?.(sessionId, term.cols, term.rows)
    } catch (e) {
      void e
    }
  }

  async function createProjectTerminal({ forceNew = false } = {}) {
    const projectPath = activeCourse?.project_path || activeTerminal?.cwd
    if (!projectPath) {
      showToast('当前项目还没有可用目录', 'error')
      return null
    }
    if (!window.windowApi?.openPowerShell) {
      showToast('当前运行环境不支持打开终端', 'error')
      return null
    }

    if (!forceNew) {
      const existing = terminalSessions.find(x => x.cwd === projectPath && x.status !== 'exited')
      if (existing) {
        setTerminalOpen(true)
        setActiveTerminalId(existing.sessionId)
        return existing
      }
    }

    try {
      setTerminalOpen(true)
      const res = await window.windowApi.openPowerShell(projectPath, {
        cols: xtermRef.current?.cols || 120,
        rows: xtermRef.current?.rows || 30,
      })
      if (res?.ok) {
        const session = {
          sessionId: res.sessionId,
          cwd: res.cwd || projectPath,
          title: res.title || `终端 ${terminalSessions.length + 1}`,
          status: 'running',
          buffer: res.buffer || '',
          cols: res.cols,
          rows: res.rows,
        }
        upsertTerminalSession(session)
        showToast(forceNew ? '已新建项目终端' : '已打开项目终端', 'success')
        return session
      } else {
        showToast('打开 PowerShell 失败', 'error')
      }
    } catch (e) {
      showToast('打开 PowerShell 失败: ' + (e?.message || e), 'error')
    }
    return null
  }

  async function openProjectTerminal() {
    return createProjectTerminal({ forceNew: false })
  }

  async function newProjectTerminal() {
    return createProjectTerminal({ forceNew: true })
  }

  async function writeTerminalInput(sessionId, input) {
    if (!sessionId || !input) return
    if (!window.windowApi?.writeTerminal) {
      showToast('当前运行环境不支持内置终端', 'error')
      return
    }
    try {
      await window.windowApi.writeTerminal(sessionId, input)
    } catch (e) {
      appendTerminalOutput(sessionId, `\n终端写入失败: ${e?.message || e}\n`)
    }
  }

  async function closeProjectTerminal(sessionId = activeTerminalId) {
    const sid = String(sessionId || '')
    if (!sid) return
    try {
      await window.windowApi?.closeTerminal?.(sid)
    } catch (e) {
      void e
    }
    const nextSessions = terminalSessions.filter(x => x.sessionId !== sid)
    terminalBuffersRef.current.delete(sid)
    setTerminalSessions(nextSessions)
    if (activeTerminalId === sid) setActiveTerminalId(nextSessions[0]?.sessionId || '')
    if (nextSessions.length === 0) setTerminalOpen(false)
  }

  async function popoutTerminal(sessionId = activeTerminalId) {
    const sid = String(sessionId || '')
    if (!sid) return
    try {
      await window.windowApi?.popoutTerminal?.(sid)
    } catch (e) {
      showToast('弹出终端失败: ' + (e?.message || e), 'error')
    }
  }

  function startTerminalResize(e) {
    e.preventDefault()
    terminalResizeStartRef.current = {
      y: e.clientY,
      height: terminalHeight,
    }
    setTerminalResizing(true)
  }

  function startTerminalPopoutDrag(e) {
    if (e.target?.closest?.('button')) return
    const sessionId = activeTerminal?.sessionId
    if (!sessionId) return
    const startX = e.clientX
    const startY = e.clientY
    let didPop = false
    const cleanup = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', cleanup)
    }
    const onMove = (moveEvent) => {
      const dx = moveEvent.clientX - startX
      const dy = moveEvent.clientY - startY
      if (!didPop && Math.sqrt(dx * dx + dy * dy) > 90) {
        didPop = true
        popoutTerminal(sessionId)
        cleanup()
      }
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', cleanup)
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

  useEffect(() => {
    if (!window.windowApi?.onTerminalEvent) return
    const unsub = window.windowApi.onTerminalEvent((event) => {
      if (!event || !event.type) return
      if (event.type === 'started') {
        setTerminalOpen(true)
        upsertTerminalSession({
          sessionId: event.sessionId,
          cwd: event.cwd || '',
          title: event.title || (event.cwd ? String(event.cwd).split(/[\\/]/).filter(Boolean).pop() : 'PowerShell'),
          status: 'running',
          buffer: '',
          cols: event.cols,
          rows: event.rows,
        })
      } else if (event.type === 'output' || event.type === 'error') {
        if (event.sessionId === xtermSessionIdRef.current && xtermRef.current) {
          xtermRef.current.write(event.data || '')
        }
        appendTerminalOutput(event.sessionId, event.data || '')
      } else if (event.type === 'exit') {
        setTerminalSessions(prev => prev.map(session => (
          session.sessionId === event.sessionId ? { ...session, status: 'exited' } : session
        )))
        const exitText = `\r\n[terminal] 已退出 code=${event.code ?? ''} signal=${event.signal ?? ''}\r\n`
        if (event.sessionId === xtermSessionIdRef.current && xtermRef.current) {
          xtermRef.current.write(exitText)
        }
        appendTerminalOutput(event.sessionId, exitText)
      } else if (event.type === 'closed') {
        terminalBuffersRef.current.delete(event.sessionId)
        setTerminalSessions(prev => {
          const next = prev.filter(session => session.sessionId !== event.sessionId)
          if (next.length === 0) setTerminalOpen(false)
          setActiveTerminalId(current => current === event.sessionId ? (next[0]?.sessionId || '') : current)
          return next
        })
      }
    })
    return () => { if (typeof unsub === 'function') unsub() }
  }, [])

  useEffect(() => {
    if (!window.windowApi?.listTerminals) return
    window.windowApi.listTerminals().then(res => {
      const sessions = Array.isArray(res?.sessions) ? res.sessions : []
      if (sessions.length > 0) {
        sessions.forEach(session => {
          if (session?.sessionId) terminalBuffersRef.current.set(session.sessionId, session.buffer || '')
        })
        setTerminalSessions(sessions)
        setActiveTerminalId(prev => prev || INITIAL_TERMINAL_SESSION_ID || sessions[0].sessionId)
        if (IS_TERMINAL_WINDOW) setTerminalOpen(true)
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    const container = terminalContainerRef.current
    if (!terminalOpen || !container || !activeTerminal?.sessionId) return

    const term = new XTerm({
      cursorBlink: true,
      convertEol: false,
      fontFamily: '"Cascadia Mono", Consolas, "Microsoft YaHei UI", monospace',
      fontSize: 13,
      lineHeight: 1.2,
      scrollback: 10000,
      theme: {
        background: '#101418',
        foreground: '#d6e2ee',
        cursor: '#d6e2ee',
        selectionBackground: '#31576f',
        black: '#1f2428',
        red: '#f97583',
        green: '#85e89d',
        yellow: '#ffea7f',
        blue: '#79b8ff',
        magenta: '#b392f0',
        cyan: '#56d4dd',
        white: '#d1d5da',
        brightBlack: '#586069',
        brightRed: '#f97583',
        brightGreen: '#85e89d',
        brightYellow: '#ffea7f',
        brightBlue: '#79b8ff',
        brightMagenta: '#b392f0',
        brightCyan: '#56d4dd',
        brightWhite: '#f6f8fa',
      },
    })
    const fitAddon = new FitAddon()
    term.loadAddon(fitAddon)
    container.replaceChildren()
    term.open(container)
    xtermRef.current = term
    fitAddonRef.current = fitAddon
    xtermSessionIdRef.current = activeTerminal.sessionId
    const initialBuffer = terminalBuffersRef.current.get(activeTerminal.sessionId) ?? activeTerminal.buffer
    if (initialBuffer) term.write(initialBuffer)
    const dataDisposable = term.onData(data => writeTerminalInput(activeTerminal.sessionId, data))
    const resizeDisposable = term.onResize(size => {
      window.windowApi?.resizeTerminal?.(activeTerminal.sessionId, size.cols, size.rows)
    })

    requestAnimationFrame(() => {
      fitActiveTerminal()
      term.focus()
    })

    return () => {
      dataDisposable.dispose()
      resizeDisposable.dispose()
      term.dispose()
      if (xtermSessionIdRef.current === activeTerminal.sessionId) {
        xtermRef.current = null
        fitAddonRef.current = null
        xtermSessionIdRef.current = ''
      }
    }
  }, [terminalOpen, activeTerminalId, activeTerminal?.sessionId])

  useEffect(() => {
    if (!terminalOpen) return
    requestAnimationFrame(() => fitActiveTerminal())
  }, [terminalOpen, terminalHeight, activeTerminalId])

  useEffect(() => {
    const container = terminalContainerRef.current
    if (!container || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => fitActiveTerminal())
    observer.observe(container)
    return () => observer.disconnect()
  }, [terminalOpen, activeTerminalId])

  useEffect(() => {
    if (!terminalResizing) return
    const onMove = (e) => {
      const start = terminalResizeStartRef.current
      if (!start) return
      const nextHeight = Math.max(180, Math.min(window.innerHeight - 180, start.height + (start.y - e.clientY)))
      setTerminalHeight(nextHeight)
    }
    const onUp = () => {
      setTerminalResizing(false)
      terminalResizeStartRef.current = null
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'ns-resize'
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
  }, [terminalResizing])

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

  const WorkspaceSidebar = () => (
    <aside className="workspace-sidebar">
      <div className="workspace-brand">
        <div className="workspace-logo"><IconLogo /></div>
        <div>
          <div className="workspace-title">Workspace</div>
          <div className="workspace-subtitle">{userId || 'user1'}</div>
        </div>
      </div>

      <button className="workspace-new-btn" onClick={newThread}>
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
                onClick={() => openThread(thread.id)}
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
            <button className="workspace-icon-btn" onClick={createProjectFromSidebar} title="新建项目">+</button>
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
                  <button className="workspace-project-main" onClick={() => openProject(course)} title={course.project_path || course.name}>
                    <IconBook />
                    <span>{course.name}</span>
                  </button>
                  <button className="workspace-icon-btn" onClick={() => newProjectThread(course)} title="新建项目对话">+</button>
                </div>
                <div className="workspace-thread-list project-thread-list">
                  {(threads.length ? threads : [createProjectChatThread(course.course_id, `course_${course.course_id}_${sessionId || 'default'}`)]).map(thread => (
                    <button
                      key={thread.id}
                      className={`workspace-thread nested ${isActiveProject && activeProjectThreadId === thread.id ? 'active' : ''}`}
                      onClick={() => openProject(course, thread.id)}
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
        <button className={`workspace-nav-btn ${page === 'companion' ? 'active' : ''}`} onClick={() => setPage('companion')}>
          <IconCompanion />
          <span>陪伴聊天</span>
        </button>
        <button className={`workspace-nav-btn ${page === 'settings' ? 'active' : ''}`} onClick={() => setPage('settings')}>
          <IconSettings />
          <span>设置</span>
        </button>
      </div>
    </aside>
  )

  if (IS_TERMINAL_WINDOW) {
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
              <button type="button" className="ghost-btn small" onClick={newProjectTerminal}>+</button>
              <button type="button" className="ghost-btn small" onClick={() => closeProjectTerminal(activeTerminal?.sessionId)}>结束</button>
            </div>
          </div>
          <div className="terminal-tabs">
            {terminalSessions.map((session, idx) => (
              <button
                key={session.sessionId}
                type="button"
                className={`terminal-tab${session.sessionId === activeTerminal?.sessionId ? ' active' : ''}`}
                onClick={() => setActiveTerminalId(session.sessionId)}
                title={session.cwd}
              >
                <span>{session.title || `终端 ${idx + 1}`}</span>
                {session.status === 'exited' && <em>已退出</em>}
              </button>
            ))}
          </div>
          <div
            className="terminal-screen"
            ref={terminalContainerRef}
            title="这是完整 PTY 终端，直接输入即可"
          />
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <Lightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />
      <WorkspaceSidebar />
      <div className="main">
        <div className="topbar">
          <span className="topbar-title">
            {page==='course_chat' ? (activeCourse?.name || '项目对话') : page==='chat' ? '无项目对话' : page==='companion' ? '陪伴聊天' : '设置'}
          </span>
          {page==='chat' && useRetrieval && <span className="topbar-tag">RAG</span>}
          {page==='chat' && useWebSearch && <span className="topbar-tag">联网</span>}
          {page==='course_chat' && activeProjectThread && <span className="topbar-tag">{activeProjectThread.title || THREAD_DEFAULT_TITLE}</span>}
          <div className="topbar-spacer"/>
          {page==='course_chat' && activeCourse && (
            <button
              title={activeCourse.project_path ? `打开项目终端：${activeCourse.project_path}` : '打开项目终端'}
              onClick={openProjectTerminal}
              className={`ghost-btn small topbar-terminal-btn${terminalOpen ? ' active' : ''}`}
            >
              <IconTerminal />
              <span>CLI</span>
            </button>
          )}
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

        {page==='chat' && (
          <>
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

        {page==='course_chat' && activeCourse && activeProjectThread && (
          <div className="course-chat-shell">
            <CourseChatPage
              key={`${activeCourse.course_id}:${activeProjectThread.id}`}
              course={activeCourse}
              backendUrl={backendUrl}
              userId={userId}
              sessionId={activeProjectThread.id}
              showToast={showToast}
              onBack={() => setPage('chat')}
              onThreadTitleChange={updateProjectThreadTitle}
            />
          </div>
        )}

        {page==='course_chat' && activeCourse && terminalOpen && (
          <div className={`terminal-panel${terminalResizing ? ' is-resizing' : ''}`} style={{ height: terminalHeight }}>
            <div
              className="terminal-resize-handle"
              title="上下拖动调整终端高度"
              onMouseDown={startTerminalResize}
            />
            <div
              className="terminal-panel-head"
              onMouseDown={startTerminalPopoutDrag}
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
                <button type="button" className="ghost-btn small" onClick={newProjectTerminal}>+</button>
                <button type="button" className="ghost-btn small" onClick={() => popoutTerminal(activeTerminal?.sessionId)}>弹出</button>
                <button type="button" className="ghost-btn small" onClick={() => setTerminalOpen(false)}>收起</button>
                <button type="button" className="ghost-btn small" onClick={() => closeProjectTerminal(activeTerminal?.sessionId)}>结束</button>
              </div>
            </div>
            <div className="terminal-tabs">
              {terminalSessions.map((session, idx) => (
                <button
                  key={session.sessionId}
                  type="button"
                  className={`terminal-tab${session.sessionId === activeTerminal?.sessionId ? ' active' : ''}`}
                  onClick={() => setActiveTerminalId(session.sessionId)}
                  title={session.cwd}
                >
                  <span>{session.title || `终端 ${idx + 1}`}</span>
                  {session.status === 'exited' && <em>已退出</em>}
                </button>
              ))}
            </div>
            <div
              className="terminal-screen"
              ref={terminalContainerRef}
              onDoubleClick={() => popoutTerminal(activeTerminal?.sessionId)}
              title="这是完整 PTY 终端，直接输入即可；双击弹出窗口"
            />
          </div>
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
              <div className="settings-card-title">模型 API</div>
              <div className="field-group">
                <div className="field">
                  <label className="field-label">API 地址</label>
                  <input
                    className="field-input"
                    value={providerDraft.api_base_url}
                    onChange={e => setProviderDraft(v => ({ ...v, api_base_url: e.target.value }))}
                    placeholder={PROVIDER_API_PLACEHOLDER}
                  />
                </div>
                <div className="field">
                  <label className="field-label">API Key</label>
                  <input
                    className="field-input"
                    type="password"
                    autoComplete="off"
                    value={providerDraft.api_key}
                    onFocus={() => {
                      if (providerDraft.api_key === MASKED_KEY_VALUE) {
                        setProviderDraft(v => ({ ...v, api_key: '' }))
                      }
                    }}
                    onChange={e => setProviderDraft(v => ({ ...v, api_key: e.target.value }))}
                    placeholder={providerSettings.has_api_key ? '已保存，输入新 Key 可替换' : 'DeepSeek API Key'}
                  />
                </div>
                <div className="provider-model-grid">
                  <div className="provider-model-item">
                    <span>轻对话模型</span>
                    <strong>{providerSettings.fast_model || '后端读取中'}</strong>
                  </div>
                  <div className="provider-model-item">
                    <span>重任务模型</span>
                    <strong>{providerSettings.heavy_model || '后端读取中'}</strong>
                  </div>
                </div>
                <div className="field-row">
                  <button className="ghost-btn" onClick={saveProviderSettings} disabled={savingProvider}>
                    {savingProvider ? '保存中' : '保存模型 API'}
                  </button>
                  <button className="ghost-btn" onClick={() => loadProviderSettings(true)} disabled={savingProvider}>
                    重新读取
                  </button>
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
    
