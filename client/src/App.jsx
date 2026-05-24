import React, { Suspense, lazy, useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Terminal as XTerm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { chatStreamApi, getProviderSettingsApi, updateProviderSettingsApi, getChatSessionApi, listCoursesApi, createCourseApi } from './api'
import CourseChatPage from './CourseChatPage'
import Chat from './app/Chat'
import Settings, { DEFAULT_PROVIDER_SETTINGS, MASKED_KEY_VALUE } from './app/Settings'
import { TerminalDock, TerminalWindow } from './app/Terminal'
import Workspace from './app/Workspace'
import { IconTerminal as TerminalIcon } from './shared/icons'
import { fileToDataUrl, estimateOutputTokens } from './shared/text'
import { Lightbox, useToast } from './shared/toast'
import { useSpeechInput } from './shared/speech'
import {
  THREAD_DEFAULT_TITLE,
  THREAD_KEY_PREFIX,
  PROJECT_THREAD_KEY_PREFIX,
  buildChatThreadTitle,
  createChatThread,
  createProjectChatThread,
  normalizeChatThreads,
  normalizeProjectThreads,
} from './shared/threads'
import '@xterm/xterm/css/xterm.css'
import './styles.css'

const CompanionChatPage = lazy(() => import('./CompanionChatPage'))
const Live2DViewer = lazy(() => import('./Live2DViewer'))
const APP_SEARCH_PARAMS = new URLSearchParams(window.location.search)
const IS_TERMINAL_WINDOW = APP_SEARCH_PARAMS.get('terminalWindow') === '1'
const IS_LIVE2D_WINDOW = APP_SEARCH_PARAMS.get('live2dWindow') === '1'
const INITIAL_TERMINAL_SESSION_ID = APP_SEARCH_PARAMS.get('sessionId') || ''
const INITIAL_LIVE2D_BG_URL = APP_SEARCH_PARAMS.get('bg') || ''

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
  const [live2dWindowBgUrl, setLive2dWindowBgUrl] = useState(INITIAL_LIVE2D_BG_URL)
  const [isMaximized, setIsMaximized] = useState(false)
  const [terminalOpen, setTerminalOpen] = useState(false)
  const [terminalSessions, setTerminalSessions] = useState([])
  const [activeTerminalId, setActiveTerminalId] = useState('')
  const [terminalHeight, setTerminalHeight] = useState(320)
  const [terminalResizing, setTerminalResizing] = useState(false)
  const [workspaceSidebarWidth, setWorkspaceSidebarWidth] = useState(() => {
    try {
      const value = Number(localStorage.getItem('workspace_sidebar_width_v1') || 292) || 292
      return Math.max(220, Math.min(520, value))
    } catch { return 292 }
  })
  const [workspaceSidebarResizing, setWorkspaceSidebarResizing] = useState(false)

  const appRef = useRef(null)
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

  useEffect(() => {
    try {
      localStorage.setItem('workspace_sidebar_width_v1', String(Math.round(workspaceSidebarWidth)))
    } catch (e) {
      void e
    }
  }, [workspaceSidebarWidth])

  useEffect(() => {
    if (!workspaceSidebarResizing) return
    const onMove = (e) => {
      const rect = appRef.current?.getBoundingClientRect()
      const left = rect?.left || 0
      const total = rect?.width || window.innerWidth
      const max = Math.max(280, Math.min(520, total - 560))
      setWorkspaceSidebarWidth(Math.max(220, Math.min(max, e.clientX - left)))
    }
    const onUp = () => setWorkspaceSidebarResizing(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    document.body.classList.add('is-pane-resizing')
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      document.body.classList.remove('is-pane-resizing')
    }
  }, [workspaceSidebarResizing])

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

  function closeProjectThread(courseId, threadId) {
    const key = String(courseId)
    const current = projectThreads[key] || []
    const remaining = current.filter(thread => thread.id !== threadId)
    const nextThreads = remaining.length > 0 ? remaining : [createProjectChatThread(courseId)]
    setProjectThreads(prev => ({ ...prev, [key]: nextThreads }))
    if (activeCourse?.course_id === courseId && activeProjectThreadId === threadId) {
      setActiveProjectThreadId(nextThreads[0].id)
    }
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

  async function runProjectCommandInTerminal(command) {
    const text = String(command || '').trim()
    if (!text) return { ok: false, error: 'empty command' }
    const session = await createProjectTerminal({ forceNew: false })
    if (!session?.sessionId) return { ok: false, error: 'terminal unavailable' }
    await writeTerminalInput(session.sessionId, text.endsWith('\r') || text.endsWith('\n') ? text : `${text}\r`)
    return { ok: true, sessionId: session.sessionId }
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

  async function openLive2DWindow() {
    if (!window.windowApi?.openLive2DWindow) {
      showToast('当前运行环境不支持弹出 Live2D', 'error')
      return
    }
    try {
      await window.windowApi.openLive2DWindow(live2dBgUrl)
      showToast('Live2D 已弹出', 'success')
    } catch (e) {
      showToast('弹出 Live2D 失败: ' + (e?.message || e), 'error')
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
    if (!IS_LIVE2D_WINDOW || !window.windowApi?.onLive2DWindowEvent) return
    const unsub = window.windowApi.onLive2DWindowEvent((event) => {
      if (event?.type === 'background') {
        setLive2dWindowBgUrl(String(event.backgroundImageUrl || ''))
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
    const userMsg = { role: 'user', content: text, created_at: new Date().toISOString() }
    const assistantId = `assistant-${Date.now()}-${Math.random().toString(36).slice(2)}`
    const patchAssistant = updater => {
      setMessages(prev => prev.map(item => {
        if (item.id !== assistantId) return item
        const patch = typeof updater === 'function' ? updater(item) : updater
        return { ...item, ...patch }
      }))
    }
    setMessages(m => [
      ...m,
      { ...userMsg, images: imgs },
      {
        id: assistantId,
        role: 'assistant',
        content: '',
        refs: [],
        activity: [],
        usage: { pending: true, output_tokens_estimate: 0 },
        model: '',
        streaming: true,
        created_at: new Date().toISOString(),
      },
    ])
    setInput(''); setPendingImages([]); setLoading(true); setLastLatency(null)
    try {
      const payload = {
        user_id: userId,
        session_id: activeThreadId,
        messages: [userMsg],
      }
      // 有图片时：把第一张 base64 作为 image_url 发给后端
      if (imgs.length > 0) payload.image_url = imgs[0]
      let doneReceived = false
      let replyText = ''
      let latestUsage = null
      let latestRefs = []
      const resp = await chatStreamApi(backendUrl, payload, {
        onDelta: (_delta, fullText) => {
          replyText = fullText
          patchAssistant(item => ({
            content: fullText,
            usage: item.usage?.pending
              ? { ...item.usage, output_tokens_estimate: estimateOutputTokens(fullText) }
              : item.usage,
            streaming: true,
          }))
        },
        onStatus: status => {
          patchAssistant(item => ({
            activity: [...(item.activity || []), status].slice(-8),
          }))
        },
        onUsage: usage => {
          latestUsage = usage
          patchAssistant({ usage })
        },
        onDone: done => {
          doneReceived = true
          replyText = done.reply || replyText
          latestUsage = done.usage || latestUsage
          latestRefs = done.reference || []
          patchAssistant({
            content: replyText,
            refs: latestRefs,
            usage: latestUsage || null,
            model: done.model || '',
            streaming: false,
            completed_at: new Date().toISOString(),
          })
          if (done.latency_ms) setLastLatency(done.latency_ms)
        },
      })
      if (!doneReceived) {
        replyText = resp.reply || replyText
        patchAssistant({
          content: replyText,
          refs: latestRefs,
          usage: latestUsage || null,
          streaming: false,
          completed_at: new Date().toISOString(),
        })
      }
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
      patchAssistant({
        content: '请求失败：' + (err?.message || err),
        refs: [],
        usage: null,
        streaming: false,
      })
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

  if (IS_TERMINAL_WINDOW) {
    return (
      <TerminalWindow
        activeTerminal={activeTerminal}
        sessions={terminalSessions}
        screenRef={terminalContainerRef}
        onSelect={setActiveTerminalId}
        onNew={newProjectTerminal}
        onClose={closeProjectTerminal}
      />
    )
  }

  if (IS_LIVE2D_WINDOW) {
    return (
      <div className="live2d-window-only">
        <div className="live2d-window-head">
          <span>Live2D</span>
        </div>
        <div className="live2d-window-body">
          <Suspense fallback={null}>
            <Live2DViewer backgroundImageUrl={live2dWindowBgUrl} />
          </Suspense>
        </div>
      </div>
    )
  }

  return (
    <div className={`app${workspaceSidebarResizing ? ' is-resizing' : ''}`} ref={appRef}>
      <Lightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />
      <Workspace
        width={workspaceSidebarWidth}
        userId={userId}
        page={page}
        activeThreadId={activeThreadId}
        sortedThreads={sortedThreads}
        onNewThread={newThread}
        onOpenThread={openThread}
        courses={courses}
        coursesLoading={coursesLoading}
        projectThreads={projectThreads}
        activeCourse={activeCourse}
        activeProjectThreadId={activeProjectThreadId}
        sessionId={sessionId}
        onCreateProject={createProjectFromSidebar}
        onOpenProject={openProject}
        onNewProjectThread={newProjectThread}
        onPage={setPage}
      />
      <div
        className="workspace-sidebar-resizer"
        onMouseDown={(e) => { e.preventDefault(); setWorkspaceSidebarResizing(true) }}
      />
      <div className="main">
        <div className="topbar">
          <span className="topbar-title">
            {page==='course_chat' ? (activeCourse?.name || '项目对话') : page==='chat' ? '无项目对话' : page==='companion' ? '陪伴聊天' : '设置'}
          </span>
          {page==='course_chat' && activeProjectThread && <span className="topbar-tag">{activeProjectThread.title || THREAD_DEFAULT_TITLE}</span>}
          <div className="topbar-spacer"/>
          {page==='course_chat' && activeCourse && (
            <button
              title={activeCourse.project_path ? `打开项目终端：${activeCourse.project_path}` : '打开项目终端'}
              onClick={openProjectTerminal}
              className={`ghost-btn small topbar-terminal-btn${terminalOpen ? ' active' : ''}`}
            >
              <TerminalIcon />
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
          <Chat
            messages={messages}
            loading={loading}
            messagesEndRef={messagesEndRef}
            composerRef={composerRef}
            textareaRef={textareaRef}
            input={input}
            setInput={setInput}
            pendingImages={pendingImages}
            setPendingImages={setPendingImages}
            isDragging={isDragging}
            setIsDragging={setIsDragging}
            listening={listening}
            onMic={handleMicClick}
            onSend={handleSend}
            onPaste={handlePaste}
            onAddImage={addImageFile}
            onImageClick={src => setLightboxSrc(src)}
            onTts={handleTtsPlay}
            canSend={canSend}
          />
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
              projectThreads={activeProjectThreads}
              activeThreadId={activeProjectThread.id}
              onOpenThread={(threadId) => openProject(activeCourse, threadId)}
              onNewThread={() => newProjectThread(activeCourse)}
              onCloseThread={(threadId) => closeProjectThread(activeCourse.course_id, threadId)}
              onInteractiveTerminalCommand={runProjectCommandInTerminal}
            />
          </div>
        )}

        {page==='course_chat' && activeCourse && terminalOpen && (
          <TerminalDock
            activeCourse={activeCourse}
            activeTerminal={activeTerminal}
            sessions={terminalSessions}
            height={terminalHeight}
            resizing={terminalResizing}
            screenRef={terminalContainerRef}
            onResizeStart={startTerminalResize}
            onDragTitle={startTerminalPopoutDrag}
            onSelect={setActiveTerminalId}
            onNew={newProjectTerminal}
            onPopout={popoutTerminal}
            onCollapse={() => setTerminalOpen(false)}
            onClose={closeProjectTerminal}
          />
        )}

        {page==='companion' && (
          <Suspense fallback={null}>
            <CompanionChatPage
              backendUrl={backendUrl}
              userId={userId}
              sessionId={sessionId}
              selectedAudioInput={selectedAudioInput}
              selectedAudioOutput={selectedAudioOutput}
              onOpenLive2D={openLive2DWindow}
              showToast={showToast}
            />
          </Suspense>
        )}
        {page==='settings' && (
          <Settings
            backendUrl={backendUrl}
            setBackendUrl={setBackendUrl}
            userId={userId}
            setUserId={setUserId}
            providerDraft={providerDraft}
            setProviderDraft={setProviderDraft}
            providerSettings={providerSettings}
            savingProvider={savingProvider}
            saveProviderSettings={saveProviderSettings}
            loadProviderSettings={loadProviderSettings}
            live2dBgUrl={live2dBgUrl}
            setLive2dBgUrl={setLive2dBgUrl}
            audioInputs={audioInputs}
            audioOutputs={audioOutputs}
            selectedAudioInput={selectedAudioInput}
            setSelectedAudioInput={setSelectedAudioInput}
            selectedAudioOutput={selectedAudioOutput}
            setSelectedAudioOutput={setSelectedAudioOutput}
            requestMicPermission={requestMicPermission}
            ttsEnabled={ttsEnabled}
            setTtsEnabled={setTtsEnabled}
          />
        )}
      </div>
      <div className={`toast ${toast.type} ${toast.visible?'show':''}`}>{toast.msg}</div>
    </div>
  )
}
    
