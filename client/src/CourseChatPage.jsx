import React, { useState, useEffect, useRef } from 'react'
import {
  listMaterialsApi,
  uploadMaterialApi,
  agentRunStreamApi,
  getMaterialViewUrl,
  getChatSessionApi,
  listWorkspaceFilesApi,
  readWorkspaceFileApi,
  saveWorkspaceFileApi,
} from './api'
import { Message, TypingIndicator } from './course/Dialog'
import {
  AttachTreeNode,
  FileTreeNode,
  collectWorkspaceFiles,
  compactOneLine,
  countTextLines,
  findWorkspaceNode,
  lineOffset,
} from './course/Files'
import OperationPanel from './course/Operations'
import {
  ATTACH_CONTEXT_FILE_CHARS,
  ATTACH_CONTEXT_MAX_CHARS,
  ATTACH_CONTEXT_MAX_FILES,
  PASTED_TEXT_CHAR_THRESHOLD,
  PASTED_TEXT_CONTEXT_MAX_CHARS,
  PASTED_TEXT_LINE_THRESHOLD,
  SELECTED_TEXT_CONTEXT_MAX_CHARS,
  buildThreadTitle,
} from './course/context'
import { estimateOutputTokens, fileNameFromPath, fileToDataUrl } from './shared/text'


export default function CourseChatPage({
  course,
  backendUrl,
  userId,
  sessionId,
  showToast,
  onBack,
  onThreadTitleChange,
  projectThreads = [],
  activeThreadId = '',
  onOpenThread,
  onNewThread,
  onCloseThread,
  onInteractiveTerminalCommand,
}) {
  const [materials, setMaterials] = useState([])
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [previewDocId, setPreviewDocId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastLatency, setLastLatency] = useState(null)
  const [pendingImages, setPendingImages] = useState([])
  const [isDragging, setIsDragging] = useState(false)
  const [uploadState, setUploadState] = useState({ title: '', file: null })
  const [uploadProgress, setUploadProgress] = useState(null)
  const [showUpload, setShowUpload] = useState(false)
  const [leftPaneWidth, setLeftPaneWidth] = useState(() => {
    try {
      const value = Number(localStorage.getItem('project_file_tree_width_v1') || 320) || 320
      return Math.max(220, Math.min(560, value))
    } catch { return 320 }
  })
  const [opsPaneWidth, setOpsPaneWidth] = useState(() => {
    try {
      const value = Number(localStorage.getItem('project_ops_pane_width_v1') || 380) || 380
      return Math.max(260, Math.min(680, value))
    } catch { return 380 }
  })
  const [resizing, setResizing] = useState(null)
  const [workspacePage, setWorkspacePage] = useState('chat')
  const [workspaceRoot, setWorkspaceRoot] = useState('')
  const [workspaceTree, setWorkspaceTree] = useState([])
  const [workspaceLoading, setWorkspaceLoading] = useState(false)
  const [openFiles, setOpenFiles] = useState([])
  const [activeFilePath, setActiveFilePath] = useState('')
  const [fileLoading, setFileLoading] = useState(false)
  const [fileSaving, setFileSaving] = useState(false)
  const [attachPickerOpen, setAttachPickerOpen] = useState(false)
  const [attachedWorkspaceItems, setAttachedWorkspaceItems] = useState([])
  const [selectedTextContext, setSelectedTextContext] = useState(null)
  const [pastedTextItems, setPastedTextItems] = useState([])
  const [pendingLineTarget, setPendingLineTarget] = useState(null)
  const [previewPageNo, setPreviewPageNo] = useState(null)

  const layoutRef = useRef(null)
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const composerRef = useRef(null)
  const attachPickerRef = useRef(null)
  const editorRef = useRef(null)
  const chatSessionId = String(sessionId || '').startsWith('course_')
    ? String(sessionId)
    : `course_${course.course_id}_${sessionId || 'default'}`
  const currentThreadId = activeThreadId || sessionId || chatSessionId
  const chatTabs = projectThreads.length
    ? projectThreads
    : [{ id: currentThreadId, title: '新对话' }]
  const activeFile = openFiles.find(file => file.path === activeFilePath) || openFiles[0] || null

  useEffect(() => {
    setOpenFiles([])
    setActiveFilePath('')
    setAttachedWorkspaceItems([])
    setSelectedTextContext(null)
    setPastedTextItems([])
    setPendingLineTarget(null)
    setPreviewPageNo(null)
    setAttachPickerOpen(false)
    fetchWorkspaceFiles()
  }, [course.course_id, backendUrl])
  useEffect(() => {
    let cancelled = false
    setMessages([])

    async function loadChatHistory() {
      try {
        const res = await getChatSessionApi(backendUrl, chatSessionId, userId)
        if (cancelled) return
        const stored = Array.isArray(res.messages) ? res.messages : []
        const visibleMessages = stored.filter(m => m?.role === 'user' || m?.role === 'assistant')
        setMessages(visibleMessages)
        const title = buildThreadTitle(visibleMessages) || (res.title === 'New chat' ? '' : res.title)
        if (title) onThreadTitleChange?.(course.course_id, chatSessionId, title)
      } catch (e) {
        void e
      }
    }

    loadChatHistory()
    return () => { cancelled = true }
  }, [backendUrl, chatSessionId, userId])
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 180) + 'px'
  }, [input])

  useEffect(() => {
    if (!pendingLineTarget || !activeFile || pendingLineTarget.path !== activeFile.path) return
    const editor = editorRef.current
    if (!editor) return
    const start = lineOffset(activeFile.content, pendingLineTarget.lineStart)
    const endLine = pendingLineTarget.lineEnd || pendingLineTarget.lineStart
    const end = lineOffset(activeFile.content, endLine + 1)
    requestAnimationFrame(() => {
      editor.focus()
      editor.setSelectionRange(start, Math.max(start, end))
      const lineHeight = 22
      editor.scrollTop = Math.max(0, (Number(pendingLineTarget.lineStart || 1) - 4) * lineHeight)
    })
    setPendingLineTarget(null)
  }, [pendingLineTarget, activeFile])

  useEffect(() => {
    if (!previewDocId) return
    const onKeyDown = (e) => {
      if (e.key === 'Escape') setPreviewDocId(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [previewDocId])

  useEffect(() => {
    if (!attachPickerOpen) return
    const onPointerDown = (e) => {
      if (!attachPickerRef.current?.contains(e.target)) setAttachPickerOpen(false)
    }
    window.addEventListener('mousedown', onPointerDown)
    return () => window.removeEventListener('mousedown', onPointerDown)
  }, [attachPickerOpen])

  useEffect(() => {
    const onKeyDown = (e) => {
      if (workspacePage !== 'files') return
      if (!(e.ctrlKey || e.metaKey) || String(e.key || '').toLowerCase() !== 's') return
      e.preventDefault()
      saveActiveFile()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [workspacePage, activeFilePath, openFiles, fileSaving])

  useEffect(() => {
    if (!resizing) return
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
    document.body.classList.add('is-pane-resizing')

    const onMove = (e) => {
      const root = layoutRef.current
      if (!root) return
      const rect = root.getBoundingClientRect()

      if (resizing === 'left') {
        const x = e.clientX - rect.left
        const maxLeft = Math.max(280, Math.min(560, rect.width - 560))
        setLeftPaneWidth(Math.max(220, Math.min(maxLeft, x)))
        return
      }

      if (resizing === 'ops') {
        const rightWidth = rect.right - e.clientX
        const maxRight = Math.max(300, rect.width - leftPaneWidth - 360)
        setOpsPaneWidth(Math.max(260, Math.min(maxRight, rightWidth)))
      }
    }

    const onUp = () => {
      setResizing(null)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
      document.body.classList.remove('is-pane-resizing')
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)

    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
      document.body.classList.remove('is-pane-resizing')
    }
  }, [resizing, leftPaneWidth])

  useEffect(() => {
    try {
      localStorage.setItem('project_file_tree_width_v1', String(Math.round(leftPaneWidth)))
    } catch (e) {
      void e
    }
  }, [leftPaneWidth])

  useEffect(() => {
    try {
      localStorage.setItem('project_ops_pane_width_v1', String(Math.round(opsPaneWidth)))
    } catch (e) {
      void e
    }
  }, [opsPaneWidth])

  async function fetchMaterials() {
    try {
      const res = await listMaterialsApi(backendUrl, course.course_id)
      setMaterials(res.items || [])
    } catch (e) {
      showToast('获取资料失败', 'error')
    }
  }

  async function fetchWorkspaceFiles() {
    setWorkspaceLoading(true)
    try {
      const res = await listWorkspaceFilesApi(backendUrl, course.course_id)
      setWorkspaceRoot(res.root || course.project_path || '')
      setWorkspaceTree(Array.isArray(res.items) ? res.items : [])
    } catch (e) {
      setWorkspaceTree([])
      showToast('读取项目文件失败: ' + (e?.message || e), 'error')
    } finally {
      setWorkspaceLoading(false)
    }
  }

  async function openWorkspaceFile(item) {
    const path = String(item?.path || '')
    if (!path) return
    const existing = openFiles.find(file => file.path === path)
    if (existing) {
      setActiveFilePath(path)
      setWorkspacePage('files')
      return
    }

    setFileLoading(true)
    try {
      const file = await readWorkspaceFileApi(backendUrl, course.course_id, path)
      setOpenFiles(prev => [...prev, {
        path: file.path,
        name: file.name || fileNameFromPath(file.path),
        content: file.content || '',
        savedContent: file.content || '',
        encoding: file.encoding || 'utf-8',
        size: Number(file.size || 0),
        modified_at: file.modified_at,
      }])
      setActiveFilePath(file.path)
      setWorkspacePage('files')
    } catch (e) {
      showToast('打开文件失败: ' + (e?.message || e), 'error')
    } finally {
      setFileLoading(false)
    }
  }

  function toWorkspaceRelativePath(path) {
    const raw = String(path || '').replace(/\\/g, '/')
    const root = String(workspaceRoot || course.project_path || '').replace(/\\/g, '/').replace(/\/+$/, '')
    if (root && raw.toLowerCase().startsWith((root + '/').toLowerCase())) {
      return raw.slice(root.length + 1)
    }
    return raw.replace(/^\/+/, '')
  }

  async function openWorkspacePath(path, lineStart = null, lineEnd = null) {
    const relPath = toWorkspaceRelativePath(path)
    if (!relPath) return
    const existing = openFiles.find(file => file.path === relPath)
    if (existing) {
      setActiveFilePath(relPath)
      setWorkspacePage('files')
      if (lineStart) setPendingLineTarget({ path: relPath, lineStart, lineEnd: lineEnd || lineStart })
      return
    }
    setFileLoading(true)
    try {
      const file = await readWorkspaceFileApi(backendUrl, course.course_id, relPath)
      setOpenFiles(prev => [...prev, {
        path: file.path,
        name: file.name || fileNameFromPath(file.path),
        content: file.content || '',
        savedContent: file.content || '',
        encoding: file.encoding || 'utf-8',
        size: Number(file.size || 0),
        modified_at: file.modified_at,
      }])
      setActiveFilePath(file.path)
      setWorkspacePage('files')
      if (lineStart) setPendingLineTarget({ path: file.path, lineStart, lineEnd: lineEnd || lineStart })
    } catch (e) {
      showToast('打开引用文件失败: ' + (e?.message || e), 'error')
    } finally {
      setFileLoading(false)
    }
  }

  function handleCitationClick(ref) {
    const target = ref?.target || {}
    const kind = ref?.type || target.kind
    const sourcePath = target.path || target.source_path || ref?.source_path || ''
    const lineStart = target.line_start || ref?.line_start
    const lineEnd = target.line_end || ref?.line_end || lineStart
    const documentId = target.document_id || ref?.document_id
    const pageNo = target.page_no || ref?.page_no || null
    const url = target.url || (kind === 'web' ? sourcePath : '')

    if (kind === 'web' && url) {
      window.open(url, '_blank', 'noopener,noreferrer')
      return
    }

    if ((kind === 'code' || kind === 'text' || lineStart) && sourcePath) {
      openWorkspacePath(sourcePath, lineStart, lineEnd)
      return
    }
    if (documentId) {
      setPreviewDocId(Number(documentId))
      setPreviewPageNo(pageNo ? Number(pageNo) : null)
      return
    }
    if (sourcePath) {
      openWorkspacePath(sourcePath, lineStart, lineEnd)
    }
  }

  function closeWorkspaceFile(path, e) {
    e?.stopPropagation?.()
    const closingFile = openFiles.find(file => file.path === path)
    if (closingFile && closingFile.content !== closingFile.savedContent) {
      const ok = window.confirm(`${closingFile.name || fileNameFromPath(path)} 还有未保存的修改，确定关闭吗？`)
      if (!ok) return
    }
    const nextFiles = openFiles.filter(file => file.path !== path)
    setOpenFiles(nextFiles)
    if (activeFilePath === path) {
      setActiveFilePath(nextFiles[0]?.path || '')
      if (nextFiles.length === 0) setWorkspacePage('chat')
    }
  }

  function openChatTab(threadId) {
    setWorkspacePage('chat')
    if (threadId && threadId !== currentThreadId) onOpenThread?.(threadId)
  }

  function closeChatTab(threadId, e) {
    e?.stopPropagation?.()
    if (onCloseThread) {
      onCloseThread(threadId || currentThreadId)
    } else {
      onBack?.()
    }
  }

  function updateActiveFileContent(value) {
    if (!activeFile) return
    setOpenFiles(prev => prev.map(file => (
      file.path === activeFile.path ? { ...file, content: value } : file
    )))
  }

  function toggleWorkspaceAttachment(item) {
    const path = String(item?.path || '')
    if (!path) return
    setAttachedWorkspaceItems(prev => {
      if (prev.some(x => x.path === path)) return prev.filter(x => x.path !== path)
      return [...prev, {
        path,
        name: item.name || fileNameFromPath(path),
        type: item.type === 'directory' ? 'directory' : 'file',
      }]
    })
  }

  function removeWorkspaceAttachment(path) {
    setAttachedWorkspaceItems(prev => prev.filter(item => item.path !== path))
  }

  function removePastedTextItem(id) {
    setPastedTextItems(prev => prev.filter(item => item.id !== id))
  }

  function captureEditorSelection(e) {
    if (!activeFile) return
    const target = e.currentTarget
    const start = Number(target.selectionStart || 0)
    const end = Number(target.selectionEnd || 0)
    if (end <= start) return
    const selected = String(target.value || '').slice(start, end)
    if (!selected.trim()) return
    const before = String(target.value || '').slice(0, start)
    const lineStart = before ? countTextLines(before) : 1
    const lineCount = countTextLines(selected)
    const lineEnd = lineStart + Math.max(lineCount - 1, 0)
    const clipped = selected.slice(0, SELECTED_TEXT_CONTEXT_MAX_CHARS)
    const name = activeFile.name || fileNameFromPath(activeFile.path)
    setSelectedTextContext({
      id: `selection:${activeFile.path}:${start}:${end}`,
      type: 'selection',
      path: activeFile.path,
      name,
      label: `selection · ${name} L${lineStart}${lineEnd !== lineStart ? `-${lineEnd}` : ''}`,
      text: clipped,
      lineStart,
      lineEnd,
      lineCount,
      charCount: selected.length,
    })
  }

  function resolveAttachedFiles(items) {
    const seen = new Set()
    const files = []
    for (const item of items || []) {
      const node = findWorkspaceNode(workspaceTree, item.path) || item
      const candidates = node.type === 'directory' ? collectWorkspaceFiles(node, []) : [node]
      for (const file of candidates) {
        if (!file?.path || seen.has(file.path)) continue
        seen.add(file.path)
        files.push(file)
      }
    }
    return files
  }

  async function buildAttachedWorkspaceContext(items) {
    const files = resolveAttachedFiles(items).slice(0, ATTACH_CONTEXT_MAX_FILES)
    if (files.length === 0) return ''

    const sections = []
    const skipped = []
    let totalChars = 0
    for (const file of files) {
      if (totalChars >= ATTACH_CONTEXT_MAX_CHARS) break
      try {
        const res = await readWorkspaceFileApi(backendUrl, course.course_id, file.path)
        const raw = String(res.content || '')
        const remaining = ATTACH_CONTEXT_MAX_CHARS - totalChars
        const content = raw.slice(0, Math.min(ATTACH_CONTEXT_FILE_CHARS, remaining))
        totalChars += content.length
        sections.push(`<file path="${res.path || file.path}">\n${content}\n</file>`)
      } catch (e) {
        skipped.push(`${file.path}: ${e?.message || e}`)
      }
    }

    if (skipped.length > 0) {
      sections.push(`<skipped>\n${skipped.slice(0, 6).join('\n')}\n</skipped>`)
    }
    if (sections.length === 0) return ''
    return `以下是用户通过项目文件选择器附加的上下文，请优先参考：\n\n${sections.join('\n\n')}`
  }

  function buildInlineTextContext(selection, pastedItems) {
    const sections = []
    if (selection?.text) {
      sections.push(`<selection path="${selection.path || ''}" lines="${selection.lineStart || 1}-${selection.lineEnd || selection.lineStart || 1}">\n${selection.text}\n</selection>`)
    }
    for (const item of pastedItems || []) {
      if (!item?.text) continue
      sections.push(`<pasted lines="${item.lineCount || countTextLines(item.text)}">\n${item.text}\n</pasted>`)
    }
    if (sections.length === 0) return ''
    return `以下是用户在编辑器中选中的文本或粘贴的大段文本，请作为本轮问题的直接上下文：\n\n${sections.join('\n\n')}`
  }

  async function saveActiveFile() {
    if (!activeFile || fileSaving) return
    setFileSaving(true)
    try {
      const res = await saveWorkspaceFileApi(backendUrl, course.course_id, {
        path: activeFile.path,
        content: activeFile.content,
        encoding: activeFile.encoding || 'utf-8',
      })
      setOpenFiles(prev => prev.map(file => (
        file.path === activeFile.path
          ? { ...file, savedContent: file.content, size: res.size, modified_at: res.modified_at }
          : file
      )))
      showToast('文件已保存', 'success')
      fetchWorkspaceFiles()
    } catch (e) {
      showToast('保存失败: ' + (e?.message || e), 'error')
    } finally {
      setFileSaving(false)
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
    const attachedForSend = [...attachedWorkspaceItems]
    const selectedForSend = selectedTextContext ? { ...selectedTextContext } : null
    const pastedForSend = [...pastedTextItems]
    if (!text && pendingImages.length === 0 && attachedForSend.length === 0 && !selectedForSend && pastedForSend.length === 0) return

    const imgs = [...pendingImages]
    const displayText = text || '请参考附加的上下文。'
    const displayAttachments = [
      ...attachedForSend,
      ...(selectedForSend ? [selectedForSend] : []),
      ...pastedForSend,
    ]
    const displayUserMsg = { role: 'user', content: displayText, attachments: displayAttachments, created_at: new Date().toISOString() }
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
      { ...displayUserMsg, images: imgs },
      {
        id: assistantId,
        role: 'assistant',
        content: '',
        refs: [],
        plan: [],
        operations: [],
        usage: { pending: true, output_tokens_estimate: 0 },
        model: '',
        streaming: true,
        created_at: new Date().toISOString(),
      },
    ])
    setInput('')
    setPendingImages([])
    setAttachedWorkspaceItems([])
    setSelectedTextContext(null)
    setPastedTextItems([])
    setAttachPickerOpen(false)
    setWorkspacePage('chat')
    setLoading(true)
    setLastLatency(null)

    try {
      const attachedContext = await buildAttachedWorkspaceContext(attachedForSend)
      const inlineContext = buildInlineTextContext(selectedForSend, pastedForSend)
      const combinedContext = [attachedContext, inlineContext].filter(Boolean).join('\n\n')
      const apiUserMsg = {
        role: 'user',
        content: combinedContext ? `${displayText}\n\n${combinedContext}` : displayText,
      }
      const docIds = Array.from(selectedIds)
      const payload = {
        user_id: userId,
        session_id: chatSessionId,
        messages: [apiUserMsg],
        use_retrieval: docIds.length > 0,
        document_ids: docIds.length > 0 ? docIds : undefined,
        workspace_path: course.project_path || workspaceRoot || undefined,
      }
      if (imgs.length > 0) payload.image_url = imgs[0]

      let doneReceived = false
      let latestText = ''
      let latestUsage = null
      let latestRefs = []
      const updateOperation = (operationId, patch) => {
        if (!operationId) return
        patchAssistant(item => ({
          operations: (item.operations || []).map(op => (
            op.id === operationId ? { ...op, ...patch } : op
          )),
        }))
      }
      const resp = await agentRunStreamApi(backendUrl, { ...payload, mode: 'plan_then_act' }, {
        onRun: run => {
          patchAssistant({ agentRun: run, agent_run_id: run?.run_id || '' })
        },
        onPlan: plan => {
          patchAssistant({ plan })
        },
        onOperation: operation => {
          patchAssistant(item => ({
            operations: [...(item.operations || []), operation],
          }))
          if (
            operation?.type === 'terminal_interactive'
            && operation.command
            && typeof onInteractiveTerminalCommand === 'function'
          ) {
            onInteractiveTerminalCommand(operation.command)
              .then(result => {
                updateOperation(operation.id, {
                  status: result?.ok ? 'launched' : 'failed',
                  terminal_session_id: result?.sessionId || '',
                  stdout: result?.ok
                    ? `已写入可见终端${result?.sessionId ? ` · ${result.sessionId}` : ''}`
                    : (result?.error || '终端启动失败'),
                })
              })
              .catch(err => {
                updateOperation(operation.id, {
                  status: 'failed',
                  stderr: String(err?.message || err || '终端启动失败'),
                })
              })
          }
        },
        onDelta: (_delta, fullText) => {
          latestText = fullText
          patchAssistant(item => ({
            content: fullText,
            usage: item.usage?.pending
              ? { ...item.usage, output_tokens_estimate: estimateOutputTokens(fullText) }
              : item.usage,
            streaming: true,
          }))
        },
        onUsage: usage => {
          latestUsage = usage
          patchAssistant({ usage })
        },
        onStatus: status => {
          patchAssistant(item => ({
            activity: [...(item.activity || []), status].slice(-8),
          }))
        },
        onDone: done => {
          doneReceived = true
          latestText = done.reply || latestText
          latestUsage = done.usage || latestUsage
          latestRefs = done.reference || []
          patchAssistant({
            content: latestText,
            refs: latestRefs,
            plan: done.plan || [],
            operations: done.operations || [],
            usage: latestUsage || null,
            model: done.model || '',
            streaming: false,
            completed_at: new Date().toISOString(),
          })
          if (done.latency_ms) setLastLatency(done.latency_ms)
        },
      })
      if (!doneReceived) {
        patchAssistant({
          content: resp.reply || latestText,
          refs: latestRefs,
          plan: resp.plan || [],
          operations: resp.operations || [],
          usage: latestUsage || null,
          streaming: false,
          completed_at: new Date().toISOString(),
        })
      }
      onThreadTitleChange?.(course.course_id, chatSessionId, buildThreadTitle([displayUserMsg]) || displayText)
      if (resp.latency_ms) setLastLatency(resp.latency_ms)
    } catch (err) {
      patchAssistant({
        content: '请求失败：' + (err?.message || err),
        refs: [],
        usage: null,
        streaming: false,
      })
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
    let handledImage = false
    for (const item of e.clipboardData?.items || []) {
      if (item.type.startsWith('image/')) {
        const f = item.getAsFile()
        if (f) {
          e.preventDefault()
          handledImage = true
          await addImageFile(f)
        }
      }
    }
    if (handledImage) return

    const pasted = e.clipboardData?.getData('text/plain') || ''
    const normalized = pasted.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trimEnd()
    if (!normalized.trim()) return
    const lineCount = countTextLines(normalized)
    if (lineCount < PASTED_TEXT_LINE_THRESHOLD && normalized.length < PASTED_TEXT_CHAR_THRESHOLD) return

    e.preventDefault()
    const clipped = normalized.slice(0, PASTED_TEXT_CONTEXT_MAX_CHARS)
    const id = `paste:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`
    setPastedTextItems(prev => [...prev, {
      id,
      type: 'paste',
      name: `pasted ${lineCount} lines`,
      label: `pasted · ${lineCount} lines`,
      text: clipped,
      lineCount,
      charCount: normalized.length,
      preview: compactOneLine(normalized),
    }])
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

  const hasInlineContext = !!selectedTextContext || pastedTextItems.length > 0
  const canSend = (input.trim() || pendingImages.length > 0 || attachedWorkspaceItems.length > 0 || hasInlineContext) && !loading
  const previewMaterial = materials.find(mat => mat.document_id === previewDocId)
  const activeFileDirty = !!activeFile && activeFile.content !== activeFile.savedContent
  const attachedPathSet = new Set(attachedWorkspaceItems.map(item => item.path))
  const hasComposerContexts = attachedWorkspaceItems.length > 0 || hasInlineContext

  return (
    <div className={`course-chat-layout${resizing ? " is-resizing" : ""}`} ref={layoutRef}>
      <div className="course-sidebar" style={{ width: leftPaneWidth, minWidth: leftPaneWidth, maxWidth: leftPaneWidth }}>
        <div className="course-sidebar-header">
          <button className="back-btn" onClick={onBack}>← 返回</button>
          <div className="course-sidebar-name" title={course.project_path || course.name}>{course.name}</div>
          <button className="ghost-btn small" onClick={fetchWorkspaceFiles} disabled={workspaceLoading}>{workspaceLoading ? '刷新中' : '刷新'}</button>
        </div>

        <div className="sidebar-section-label">项目文件</div>
        <div className="workspace-file-tree sidebar-file-tree">
          {workspaceLoading && <div className="workspace-file-empty">正在读取项目文件...</div>}
          {!workspaceLoading && workspaceTree.length === 0 && <div className="workspace-file-empty">项目目录暂无文件</div>}
          {!workspaceLoading && workspaceTree.map(item => (
            <FileTreeNode
              key={`${item.type}:${item.path}`}
              item={item}
              activePath={activeFilePath}
              openFile={openWorkspaceFile}
            />
          ))}
        </div>
      </div>

      <div className="pane-resizer" onMouseDown={(e) => { e.preventDefault(); setResizing('left') }} />

      <div className="course-chat-right">
        <div className="chat-panel">
          <div className="topbar project-editor-topbar">
            <div className="project-window-tabs">
              {chatTabs.map(thread => (
                <button
                  key={thread.id}
                  type="button"
                  className={`project-window-tab chat-tab${workspacePage === 'chat' && thread.id === currentThreadId ? ' active' : ''}`}
                  onClick={() => openChatTab(thread.id)}
                  title={thread.title || '新对话'}
                >
                  <span>{thread.title || '新对话'}</span>
                  <b onClick={(e) => closeChatTab(thread.id, e)}>x</b>
                </button>
              ))}
              {openFiles.map(file => (
                <button
                  key={file.path}
                  type="button"
                  className={`project-window-tab file-tab${workspacePage === 'files' && file.path === activeFile?.path ? ' active' : ''}${file.content !== file.savedContent ? ' dirty' : ''}`}
                  onClick={() => { setActiveFilePath(file.path); setWorkspacePage('files') }}
                  title={file.path}
                >
                  <span>{file.name || fileNameFromPath(file.path)}</span>
                  {file.content !== file.savedContent && <em>*</em>}
                  <b onClick={(e) => closeWorkspaceFile(file.path, e)}>x</b>
                </button>
              ))}
            </div>
            <div className="topbar-spacer" />
            <button className="ghost-btn small project-window-add" onClick={() => onNewThread?.()} title="新建对话窗口">+</button>
            {workspacePage === 'files' && (
              <button className="ghost-btn small" onClick={saveActiveFile} disabled={!activeFileDirty || fileSaving}>{fileSaving ? '保存中' : activeFileDirty ? '保存 *' : '已保存'}</button>
            )}
            {workspacePage === 'chat' && (
              <span className={`topbar-status ${loading ? 'loading' : ''}`}>
                {loading ? '生成中…' : lastLatency ? `${lastLatency} ms` : 'ready'}
              </span>
            )}
          </div>

          {workspacePage === 'files' && (
            <div className="workspace-editor-page">
              <div className="workspace-editor-main">
                {fileLoading && <div className="workspace-editor-empty">正在打开文件...</div>}
                {!fileLoading && activeFile && (
                  <>
                    <div className="workspace-editor-meta">
                      <span title={activeFile.path}>{activeFile.path}</span>
                      <code>{activeFile.encoding || 'utf-8'}</code>
                    </div>
                    <textarea
                      ref={editorRef}
                      className="workspace-code-editor"
                      value={activeFile.content}
                      spellCheck={false}
                      onChange={e => updateActiveFileContent(e.target.value)}
                      onSelect={captureEditorSelection}
                      onMouseUp={captureEditorSelection}
                      onKeyUp={captureEditorSelection}
                    />
                  </>
                )}
                {!fileLoading && !activeFile && (
                  <div className="workspace-editor-empty">从左侧文件树选择一个文本文件打开</div>
                )}
              </div>
            </div>
          )}

          <div
            className={`project-agent-split${workspacePage !== 'chat' ? ' hidden' : ''}`}
            style={{ gridTemplateColumns: `minmax(0, 1fr) 8px ${opsPaneWidth}px` }}
          >
            <div className="chat-area project-chat-scroll project-agent-dialogue">
              {messages.length === 0 && (
                <div className="chat-empty">
                  <div className="chat-empty-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="22" height="22" strokeWidth="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  </div>
                  <p>左侧显示问答、计划和总结；右侧显示终端输出与代码片段</p>
                </div>
              )}
              {messages.map((m, i) => <Message key={i} m={m} onCitationClick={handleCitationClick} />)}
              {loading && !messages.some(m => m.streaming) && (
                <>
                  <TypingIndicator />
                  <div className="token-usage live">tokens 统计中 · cache -- · out --</div>
                </>
              )}
              <div ref={messagesEndRef} />
            </div>
            <div className="agent-ops-resizer" onMouseDown={(e) => { e.preventDefault(); setResizing('ops') }} />
            <OperationPanel messages={messages} />
          </div>

          <div className={`composer-wrap project-composer${isDragging ? ' drag-over' : ''}`} ref={composerRef}
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
                {hasComposerContexts && (
                  <div className="composer-context-chips">
                    {attachedWorkspaceItems.map(item => (
                      <button
                        key={`${item.type}:${item.path}`}
                        type="button"
                        className="composer-context-chip"
                        onClick={() => removeWorkspaceAttachment(item.path)}
                        title={`${item.path} · 点击移除`}
                      >
                        <span>{item.type === 'directory' ? '文件夹' : '文件'} · {item.name || fileNameFromPath(item.path)}</span>
                        <b>x</b>
                      </button>
                    ))}
                    {selectedTextContext && (
                      <button
                        type="button"
                        className="composer-context-chip selected-text"
                        onClick={() => setSelectedTextContext(null)}
                        title={`${selectedTextContext.path || ''} · ${selectedTextContext.lineCount || 1} lines · 点击移除`}
                      >
                        <span>{selectedTextContext.label || 'selection'}</span>
                        <b>x</b>
                      </button>
                    )}
                    {pastedTextItems.map(item => (
                      <button
                        key={item.id}
                        type="button"
                        className="composer-context-chip pasted-text"
                        onClick={() => removePastedTextItem(item.id)}
                        title={`${item.preview || item.name} · 点击移除`}
                      >
                        <span>{item.label || item.name}</span>
                        <b>x</b>
                      </button>
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
                  <div className="composer-attach-picker" ref={attachPickerRef}>
                    <button
                      type="button"
                      className={`composer-icon-btn${attachPickerOpen ? ' active' : ''}`}
                      title="添加项目文件或文件夹"
                      onClick={() => setAttachPickerOpen(v => !v)}
                    >
                      +
                    </button>
                    {attachPickerOpen && (
                      <div className="attach-picker-popover">
                        <div className="attach-picker-head">
                          <strong>添加上下文</strong>
                          <button type="button" onClick={() => setAttachedWorkspaceItems([])}>清空</button>
                        </div>
                        <div className="attach-picker-list">
                          {workspaceLoading && <div className="workspace-file-empty">正在读取项目文件...</div>}
                          {!workspaceLoading && workspaceTree.length === 0 && <div className="workspace-file-empty">项目目录暂无文件</div>}
                          {!workspaceLoading && workspaceTree.map(item => (
                            <AttachTreeNode
                              key={`${item.type}:${item.path}`}
                              item={item}
                              selectedPaths={attachedPathSet}
                              toggleAttach={toggleWorkspaceAttachment}
                            />
                          ))}
                        </div>
                        <div className="attach-picker-foot">
                          <span>{attachedWorkspaceItems.length} 项已选</span>
                          <button type="button" onClick={() => setAttachPickerOpen(false)}>完成</button>
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="composer-spacer" />
                  <button className="send-btn" onClick={handleSend} disabled={!canSend} title="发送">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="14" height="14"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
                  </button>
                </div>
              </div>
          </div>
        </div>
      </div>

      {previewDocId && (
        <div className="preview-modal-backdrop" onClick={() => { setPreviewDocId(null); setPreviewPageNo(null) }}>
          <div className="preview-modal" onClick={e => e.stopPropagation()}>
            <div className="preview-modal-head">
              <div className="preview-modal-title">
                <span>项目文件预览</span>
                <strong title={previewMaterial?.source_path || previewMaterial?.title || ''}>
                  {previewMaterial?.title || `文件 ${previewDocId}`}
                </strong>
              </div>
              <button className="preview-modal-close" onClick={() => { setPreviewDocId(null); setPreviewPageNo(null) }} title="关闭预览">×</button>
            </div>
            <iframe className="preview-modal-frame" src={`${getMaterialViewUrl(backendUrl, previewDocId)}?inline=1${previewPageNo ? `#page=${previewPageNo}` : ''}`} title="project file preview" />
          </div>
        </div>
      )}
    </div>
  )
}
