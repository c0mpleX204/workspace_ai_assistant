import React, { useState, useEffect, useRef } from 'react'
import {
  listMaterialsApi,
  uploadMaterialApi,
  agentRunStreamApi,
  personaApplyStreamApi,
  getMaterialViewUrl,
  getChatSessionApi,
  listWorkspaceFilesApi,
  createWorkspaceFileApi,
  createWorkspaceDirectoryApi,
  deleteWorkspaceFileApi,
  deleteWorkspaceDirectoryApi,
  renameWorkspaceItemApi,
  getWorkspaceFileRawUrl,
} from './api'
import { Message, TypingIndicator } from './course/Dialog'
import {
  FileTreeNode,
  AttachTreeNode,
  collectWorkspaceFiles,
  compactOneLine,
  countTextLines,
} from './course/Files'
import { estimateOutputTokens, fileNameFromPath, fileToDataUrl } from './shared/text'
import { loadRuntimeFlags, trySlashCommand } from './shared/slashCommands'

import PdfViewer from './shared/PdfViewer'

const PASTED_TEXT_LINE_THRESHOLD = 4
const PASTED_TEXT_CHAR_THRESHOLD = 900
const PASTED_TEXT_CONTEXT_MAX_CHARS = 60000

function normalizePathForMatch(value) {
  return String(value || '')
    .replace(/\\/g, '/')
    .replace(/\/+/g, '/')
    .replace(/^\/+/, '')
    .toLowerCase()
}

function pureConversationMessages(items) {
  return (items || [])
    .filter(item => item?.role === 'user' || item?.role === 'assistant')
    .filter(item => !item?.metadata?.transient_persona_apply)
    .map(item => ({
      role: item.role,
      content: String(item.content || '').trim(),
    }))
    .filter(item => item.content)
}


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
  onPdfViewChange,
  onInteractiveTerminalCommand,
  personaApplyRequest,
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
  const [fileTreeDragOver, setFileTreeDragOver] = useState(false)
  const [importingFiles, setImportingFiles] = useState(false)
  const [rootCreating, setRootCreating] = useState(null)
  const [rootCreateValue, setRootCreateValue] = useState('')
  const [fileTreeContextMenu, setFileTreeContextMenu] = useState(null)
  const [uploadState, setUploadState] = useState({ title: '', file: null })
  const [uploadProgress, setUploadProgress] = useState(null)
  const [showUpload, setShowUpload] = useState(false)
  const [leftPaneWidth, setLeftPaneWidth] = useState(() => {
    try {
      const value = Number(localStorage.getItem('project_file_tree_width_v1') || 320) || 320
      return Math.max(220, Math.min(560, value))
    } catch { return 320 }
  })
  const [resizing, setResizing] = useState(null)
  const [workspaceRoot, setWorkspaceRoot] = useState('')
  const [workspaceTree, setWorkspaceTree] = useState([])
  const [workspaceLoading, setWorkspaceLoading] = useState(false)
  const [pastedTextItems, setPastedTextItems] = useState([])
  const [showFilePicker, setShowFilePicker] = useState(false)
  const [filePickerSelected, setFilePickerSelected] = useState(new Set())
  const [attachedFiles, setAttachedFiles] = useState([])
  const [previewPageNo, setPreviewPageNo] = useState(null)
  const [pdfView, setPdfView] = useState({ active: false, docId: null, url: '', initialPage: 1, threadId: '' })

  function openPdfInline(docId, url, initialPage = 1) {
    setPdfView({ active: true, docId, url, initialPage, threadId: `pdf_${course.course_id}_${docId}` })
    onPdfViewChange?.(true)
  }

  function closePdfInline() {
    setPdfView({ active: false, docId: null, url: '', initialPage: 1, threadId: '' })
    onPdfViewChange?.(false)
  }

  const layoutRef = useRef(null)
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const composerRef = useRef(null)
  const rootCreatingGuardRef = useRef(false)
  const personaApplyRequestIdRef = useRef('')
  const chatSessionId = String(sessionId || '').startsWith('course_')
    ? String(sessionId)
    : `course_${course.course_id}_${sessionId || 'default'}`
  const currentThreadId = activeThreadId || sessionId || chatSessionId
  const chatTabs = projectThreads.length
    ? projectThreads
    : [{ id: currentThreadId, title: '新对话' }]

  useEffect(() => {
    setPastedTextItems([])
    setPreviewPageNo(null)
    fetchMaterials()
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
    const requestId = personaApplyRequest?.id
    if (!requestId || personaApplyRequestIdRef.current === requestId) return
    personaApplyRequestIdRef.current = requestId
    applyPersonaToProjectChat(personaApplyRequest.persona)
  }, [personaApplyRequest])

  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 180) + 'px'
  }, [input])

  useEffect(() => {
    if (!previewDocId) return
    const onKeyDown = (e) => {
      if (e.key === 'Escape') setPreviewDocId(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [previewDocId])

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
    } catch (e) { void e }
  }, [leftPaneWidth])

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

  function openFileInVSCode(item) {
    // only used from right-click context menu
    const relPath = String(item?.path || '')
    if (!relPath) return
    const root = workspaceRoot || course.project_path || ''
    const fullPath = root ? `${root.replace(/\\/g, '/').replace(/\/+$/, '')}/${relPath}` : relPath
    if (window.windowApi?.openInVSCode) {
      window.windowApi.openInVSCode(fullPath).catch(() => {
        showToast('无法打开 VS Code，请确认已安装并在 PATH 中', 'error')
      })
    } else {
      showToast('VS Code 集成仅在桌面客户端可用', 'error')
    }
  }

  function handleFileClick(item) {
    if (!item || item.type === 'directory') return
    const name = String(item.name || '')
    const relPath = String(item.path || '')
    if (!relPath) return
    if (name.toLowerCase().endsWith('.pdf')) {
      const normalizedRel = normalizePathForMatch(relPath)
      const indexedMaterial = materials.find(mat => {
        if (String(mat.file_type || '').toLowerCase() !== 'pdf') return false
        const source = normalizePathForMatch(mat.source_path)
        return source === normalizedRel || source.endsWith(`/${normalizedRel}`)
      })
      if (indexedMaterial?.document_id) {
        openPdfInline(Number(indexedMaterial.document_id), getMaterialViewUrl(backendUrl, Number(indexedMaterial.document_id)), 1)
      } else {
        const url = getWorkspaceFileRawUrl(backendUrl, course.course_id, relPath)
        const docId = 'ws_' + encodeURIComponent(relPath)
        openPdfInline(docId, url, 1)
      }
    }
  }

  function handleCitationClick(ref) {
    const target = ref?.target || {}
    const kind = ref?.type || target.kind
    const sourcePath = target.path || target.source_path || ref?.source_path || ''
    const lineStart = target.line_start || ref?.line_start
    const documentId = target.document_id || ref?.document_id
    const pageNo = target.page_no || ref?.page_no || null
    const url = target.url || (kind === 'web' ? sourcePath : '')

    if (kind === 'web' && url) {
      window.open(url, '_blank', 'noopener,noreferrer')
      return
    }

    if ((kind === 'code' || kind === 'text' || lineStart) && sourcePath) {
      const root = workspaceRoot || course.project_path || ''
      const fullPath = root ? `${root.replace(/\\/g, '/').replace(/\/+$/, '')}/${sourcePath}` : sourcePath
      if (window.windowApi?.openInVSCode) {
        window.windowApi.openInVSCode(fullPath).catch(() => {})
      }
      return
    }
    if (documentId) {
      const mat = materials.find(m => m.document_id === Number(documentId))
      if (mat?.file_type === 'pdf') {
        openPdfInline(Number(documentId), getMaterialViewUrl(backendUrl, Number(documentId)), pageNo ? Number(pageNo) : 1)
      } else {
        setPreviewDocId(Number(documentId))
        setPreviewPageNo(pageNo ? Number(pageNo) : null)
      }
      return
    }
    if (sourcePath) {
      const root = workspaceRoot || course.project_path || ''
      const fullPath = root ? `${root.replace(/\\/g, '/').replace(/\/+$/, '')}/${sourcePath}` : sourcePath
      if (window.windowApi?.openInVSCode) {
        window.windowApi.openInVSCode(fullPath).catch(() => {})
      }
    }
  }

  function closeChatTab(threadId, e) {
    e?.stopPropagation?.()
    if (onCloseThread) {
      onCloseThread(threadId || currentThreadId)
    } else {
      onBack?.()
    }
  }

  function removePastedTextItem(id) {
    setPastedTextItems(prev => prev.filter(item => item.id !== id))
  }

  function removeAttachedFile(id) {
    setAttachedFiles(prev => prev.filter(item => item.id !== id))
  }

  function toggleFilePickerSelect(item) {
    if (item.type === 'directory') {
      const files = collectWorkspaceFiles(item)
      setFilePickerSelected(prev => {
        const next = new Set(prev)
        const allSelected = files.every(f => prev.has(f.path))
        for (const f of files) {
          if (allSelected) next.delete(f.path)
          else next.add(f.path)
        }
        return next
      })
    } else {
      setFilePickerSelected(prev => {
        const next = new Set(prev)
        if (next.has(item.path)) next.delete(item.path)
        else next.add(item.path)
        return next
      })
    }
  }

  async function fetchFileContent(filePath) {
    const url = getWorkspaceFileRawUrl(backendUrl, course.course_id, filePath)
    const resp = await fetch(url)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return await resp.text()
  }

  async function confirmFileAttach() {
    const paths = Array.from(filePickerSelected)
    if (paths.length === 0) { setShowFilePicker(false); return }

    const newFiles = []
    for (const path of paths) {
      try {
        const content = await fetchFileContent(path)
        const name = fileNameFromPath(path)
        const clipped = content.slice(0, PASTED_TEXT_CONTEXT_MAX_CHARS)
        const lineCount = countTextLines(clipped)
        newFiles.push({
          id: `file:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
          type: 'file',
          path,
          name,
          label: `file · ${name}`,
          text: clipped,
          lineCount,
          charCount: content.length,
          preview: compactOneLine(clipped),
        })
      } catch (e) {
        showToast(`读取文件失败: ${path}`, 'error')
      }
    }

    setAttachedFiles(prev => [...prev, ...newFiles])
    setFilePickerSelected(new Set())
    setShowFilePicker(false)
  }

  function buildInlineTextContext(pastedItems, fileItems) {
    const sections = []
    for (const item of pastedItems || []) {
      if (!item?.text) continue
      sections.push(`<pasted lines="${item.lineCount || countTextLines(item.text)}">\n${item.text}\n</pasted>`)
    }
    for (const item of fileItems || []) {
      if (!item?.text) continue
      sections.push(`<attached_file path="${item.path}" lines="${item.lineCount}">\n${item.text}\n</attached_file>`)
    }
    if (sections.length === 0) return ''
    return `以下是用户提供的额外上下文：\n\n${sections.join('\n\n')}`
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

  async function applyPersonaToProjectChat(persona) {
    const prompt = String(persona?.content || '').trim()
    if (!prompt) {
      showToast('这个人设 md 还没有可用内容', 'error')
      return
    }
    if (loading) {
      showToast('当前项目对话正在生成，稍后再应用人设', 'error')
      return
    }

    let sourceMessages = messages
    if (pureConversationMessages(sourceMessages).length === 0) {
      try {
        const res = await getChatSessionApi(backendUrl, chatSessionId, userId)
        const stored = Array.isArray(res.messages) ? res.messages : []
        const visibleMessages = stored.filter(m => m?.role === 'user' || m?.role === 'assistant')
        if (visibleMessages.length > 0) {
          sourceMessages = visibleMessages
          setMessages(visibleMessages)
        }
      } catch (e) {
        void e
      }
    }

    const cleanMessages = pureConversationMessages(sourceMessages)
    if (cleanMessages.length === 0) {
      showToast('当前项目会话还没有用户/AI 对话可处理', 'error')
      return
    }

    const assistantId = `persona-${Date.now()}-${Math.random().toString(36).slice(2)}`
    const patchAssistant = updater => {
      setMessages(prev => prev.map(item => {
        if (item.id !== assistantId) return item
        const patch = typeof updater === 'function' ? updater(item) : updater
        return { ...item, ...patch }
      }))
    }

    setLoading(true)
    setLastLatency(null)
    setMessages(prev => [
      ...prev,
      {
        id: assistantId,
        role: 'assistant',
        content: '',
        refs: [],
        plan: [],
        operations: [],
        activity: [],
        usage: { pending: true, output_tokens_estimate: 0 },
        model: '',
        streaming: true,
        created_at: new Date().toISOString(),
        metadata: {
          persona_id: persona.id || '',
          persona_name: persona.name || persona.id || '',
          transient_persona_apply: true,
        },
      },
    ])

    try {
      let doneReceived = false
      let latestText = ''
      let latestUsage = null
      const resp = await personaApplyStreamApi(backendUrl, {
        user_id: userId,
        session_id: chatSessionId,
        persona_prompt: prompt,
        messages: cleanMessages,
        persist_to_session: true,
      }, {
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
        onDone: done => {
          doneReceived = true
          latestText = done.reply || latestText
          latestUsage = done.usage || latestUsage
          patchAssistant({
            content: latestText,
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
          usage: latestUsage || null,
          model: resp.model || '',
          streaming: false,
          completed_at: new Date().toISOString(),
        })
      }
      if (resp.latency_ms) setLastLatency(resp.latency_ms)
    } catch (err) {
      patchAssistant({
        content: '人设处理失败：' + (err?.message || err),
        refs: [],
        usage: null,
        streaming: false,
      })
      showToast('人设处理失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  async function handleSend() {
    const text = input.trim()
    const pastedForSend = [...pastedTextItems]
    const filesForSend = [...attachedFiles]
    if (!text && pendingImages.length === 0 && pastedForSend.length === 0 && filesForSend.length === 0) return

    const imgs = [...pendingImages]
    const displayText = text || '请参考附加的上下文。'
    const displayAttachments = [...pastedForSend, ...filesForSend]
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
    setPastedTextItems([])
    setAttachedFiles([])
    setLoading(true)
    setLastLatency(null)

    try {
      const inlineContext = buildInlineTextContext(pastedForSend, filesForSend)
      const apiUserMsg = {
        role: 'user',
        content: inlineContext ? `${displayText}\n\n${inlineContext}` : displayText,
      }
      const docIds = Array.from(selectedIds)
      const rtFlags = loadRuntimeFlags()
      const payload = {
        user_id: userId,
        session_id: chatSessionId,
        messages: [apiUserMsg],
        use_retrieval: docIds.length > 0,
        document_ids: docIds.length > 0 ? docIds : undefined,
        workspace_path: course.project_path || workspaceRoot || undefined,
        thinking_enabled: rtFlags.thinking_enabled,
        subagent_enabled: rtFlags.subagent_enabled,
        function_calling_enabled: rtFlags.fc_enabled,
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
      const cmd = trySlashCommand(input)
      if (cmd.handled) {
        setInput('')
        showToast(cmd.message, cmd.message.includes('ON') ? 'success' : 'info')
        return
      }
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
      if (String(res.file_type || '').toLowerCase() === 'pdf' && res.document_id) {
        openPdfInline(Number(res.document_id), getMaterialViewUrl(backendUrl, Number(res.document_id)), 1)
      } else {
        setPreviewDocId(res.document_id)
      }
    } catch (err) {
      setUploadProgress(null)
      showToast('上传失败：' + (err?.message || err), 'error')
    }
  }

  async function handleImportFiles(files) {
    const fileList = Array.from(files || [])
    if (fileList.length === 0) return
    setImportingFiles(true)
    let ok = 0
    let fail = 0
    for (const file of fileList) {
      try {
        const form = new FormData()
        form.append('course_id', course.course_id)
        form.append('title', file.name)
        form.append('file', file)
        await uploadMaterialApi(backendUrl, form)
        ok++
      } catch (e) {
        fail++
        void e
      }
    }
    setImportingFiles(false)
    if (ok > 0) {
      showToast(`导入完成：${ok} 个成功${fail > 0 ? `，${fail} 个失败` : ''}`, fail > 0 ? 'error' : 'success')
      fetchMaterials()
      fetchWorkspaceFiles()
    } else {
      showToast('导入失败', 'error')
    }
  }

  function handleFileTreeDragOver(e) {
    e.preventDefault()
    e.stopPropagation()
    setFileTreeDragOver(true)
  }

  function handleFileTreeDragLeave(e) {
    e.preventDefault()
    e.stopPropagation()
    setFileTreeDragOver(false)
  }

  function handleFileTreeContextMenu(e) {
    e.preventDefault()
    setFileTreeContextMenu({ x: e.clientX, y: e.clientY })
  }

  function handleFileTreeDrop(e) {
    e.preventDefault()
    e.stopPropagation()
    setFileTreeDragOver(false)
    handleImportFiles(e.dataTransfer.files)
  }

  function handleImportClick(e) {
    e.preventDefault()
    e.stopPropagation()
    const input = document.createElement('input')
    input.type = 'file'
    input.multiple = true
    input.onchange = () => {
      if (input.files && input.files.length > 0) {
        handleImportFiles(input.files)
      }
      input.remove()
    }
    input.click()
  }

  async function handleRootCreateConfirm() {
    if (rootCreatingGuardRef.current) return
    rootCreatingGuardRef.current = true
    const type = rootCreating
    const val = rootCreateValue.trim()
    setRootCreating(null)
    setRootCreateValue('')
    if (!val || !type) { rootCreatingGuardRef.current = false; return }
    if (type === 'file') {
      await handleCreateFile('', val)
    } else {
      await handleCreateFolder('', val)
    }
    rootCreatingGuardRef.current = false
  }

  function handleRootCreateCancel() {
    if (rootCreatingGuardRef.current) return
    setRootCreating(null)
    setRootCreateValue('')
  }

  async function handleCreateFile(parentPath, name) {
    try {
      const filePath = parentPath ? `${parentPath}/${name}` : name
      await createWorkspaceFileApi(backendUrl, course.course_id, { path: filePath, content: '' })
      showToast(`文件 ${name} 已创建`, 'success')
      fetchWorkspaceFiles()
    } catch (e) {
      showToast('创建文件失败: ' + (e?.message || e), 'error')
    }
  }

  async function handleCreateFolder(parentPath, name) {
    try {
      const folderPath = parentPath ? `${parentPath}/${name}` : name
      await createWorkspaceDirectoryApi(backendUrl, course.course_id, { path: folderPath })
      showToast(`文件夹 ${name} 已创建`, 'success')
      fetchWorkspaceFiles()
    } catch (e) {
      showToast('创建文件夹失败: ' + (e?.message || e), 'error')
    }
  }

  async function handleDeleteItem(item) {
    if (!window.confirm(`确定删除 ${item.name}？${item.type === 'directory' ? '将同时删除目录下所有文件。' : ''}`)) return
    try {
      if (item.type === 'directory') {
        await deleteWorkspaceDirectoryApi(backendUrl, course.course_id, item.path, true)
      } else {
        await deleteWorkspaceFileApi(backendUrl, course.course_id, item.path)
      }
      showToast(`${item.name} 已删除`, 'success')
      fetchWorkspaceFiles()
    } catch (e) {
      showToast('删除失败: ' + (e?.message || e), 'error')
    }
  }

  async function handleRenameItem(item, newName) {
    try {
      const parts = item.path.split('/')
      parts[parts.length - 1] = newName
      const targetPath = parts.join('/')
      await renameWorkspaceItemApi(backendUrl, course.course_id, { source_path: item.path, target_path: targetPath })
      showToast(`已重命名为 ${newName}`, 'success')
      fetchWorkspaceFiles()
    } catch (e) {
      showToast('重命名失败: ' + (e?.message || e), 'error')
    }
  }

  function buildThreadTitle(messages) {
    for (const m of messages || []) {
      if (m?.role !== 'user') continue
      const t = String(m.content || '').trim()
      if (t) return t.length > 40 ? t.slice(0, 37) + '...' : t
    }
    return ''
  }

  const hasInlineContext = pastedTextItems.length > 0 || attachedFiles.length > 0
  const canSend = (input.trim() || pendingImages.length > 0 || hasInlineContext) && !loading
  const previewMaterial = materials.find(mat => mat.document_id === previewDocId)

  return (
    <div className={`course-chat-layout${resizing ? " is-resizing" : ""}`} ref={layoutRef}>
      <div className="course-sidebar" style={{ width: leftPaneWidth, minWidth: leftPaneWidth, maxWidth: leftPaneWidth }}>
        <div className="course-sidebar-header">
          <button className="back-btn" onClick={onBack}>← 返回</button>
          <div className="course-sidebar-name" title={course.project_path || course.name}>{course.name}</div>
          <div style={{display:'flex',gap:2,alignItems:'center'}}>
            <button className="sidebar-icon-btn" onClick={() => { setRootCreating('file'); setRootCreateValue('') }} title="新建文件" disabled={workspaceLoading}>
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" width="14" height="14" strokeWidth="1.3"><path d="M3 2.5h6l4 4V13a.5.5 0 0 1-.5.5h-9a.5.5 0 0 1-.5-.5V3a.5.5 0 0 1 .5-.5z"/><path d="M9 2.5V6h3.5"/><line x1="6" y1="8.5" x2="10" y2="8.5"/><line x1="6" y1="10.5" x2="10" y2="10.5"/></svg>
            </button>
            <button className="sidebar-icon-btn" onClick={() => { setRootCreating('folder'); setRootCreateValue('') }} title="新建文件夹" disabled={workspaceLoading}>
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" width="14" height="14" strokeWidth="1.3"><path d="M1.5 3.5h4.5l1 1.5h5.5a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H2.5a1 1 0 0 1-1-1V3.5z"/><line x1="6" y1="8.5" x2="10" y2="8.5"/><line x1="8" y1="6.5" x2="8" y2="10.5"/></svg>
            </button>
            <button className="sidebar-icon-btn" onClick={handleImportClick} title="导入文件到工作区" disabled={importingFiles}>{importingFiles ? '...' : '↑'}</button>
          </div>
        </div>

        <div className="sidebar-section-label">项目文件</div>
        <div
          className={`workspace-file-tree sidebar-file-tree${fileTreeDragOver ? ' drag-over' : ''}`}
          onDragOver={handleFileTreeDragOver}
          onDragLeave={handleFileTreeDragLeave}
          onDrop={handleFileTreeDrop}
          onContextMenu={handleFileTreeContextMenu}
        >
          {importingFiles && <div className="workspace-file-empty">正在导入文件...</div>}
          {!importingFiles && workspaceLoading && <div className="workspace-file-empty">正在读取项目文件...</div>}
          {!importingFiles && !workspaceLoading && workspaceTree.length === 0 && (
            <div className="workspace-file-empty">
              <div>项目目录暂无文件</div>
              <div style={{fontSize:12,color:'var(--text-muted)',marginTop:4}}>拖拽文件到此处导入，或点击上方 ↑ 按钮</div>
            </div>
          )}
          {!importingFiles && !workspaceLoading && rootCreating && (
            <div className="workspace-file-node">
              <div className="workspace-file-row creating" style={{ paddingLeft: 8 }}>
                <span className="workspace-file-icon">{rootCreating === 'folder' ? '▸' : '•'}</span>
                <input
                  className="workspace-inline-input"
                  value={rootCreateValue}
                  placeholder={rootCreating === 'file' ? '新建文件...' : '新建文件夹...'}
                  onChange={e => setRootCreateValue(e.target.value)}
                  onBlur={handleRootCreateCancel}
                  onKeyDown={e => {
                    if (e.key === 'Enter') handleRootCreateConfirm()
                    if (e.key === 'Escape') { setRootCreating(null); setRootCreateValue(''); rootCreatingGuardRef.current = false }
                  }}
                  autoFocus
                />
              </div>
            </div>
          )}
          {!importingFiles && !workspaceLoading && workspaceTree.map(item => (
            <FileTreeNode
              key={`${item.type}:${item.path}`}
              item={item}
              activePath={null}
              openFile={handleFileClick}
              openInVSCode={openFileInVSCode}
              onCreateFile={handleCreateFile}
              onCreateFolder={handleCreateFolder}
              onDelete={handleDeleteItem}
              onRename={handleRenameItem}
            />
          ))}
        </div>

      </div>

      {fileTreeContextMenu && (
        <>
          <div className="context-menu-backdrop" onClick={() => setFileTreeContextMenu(null)} onContextMenu={e => { e.preventDefault(); setFileTreeContextMenu(null) }} />
          <div className="context-menu" style={{ left: fileTreeContextMenu.x, top: fileTreeContextMenu.y }}>
            <button className="context-menu-item" onClick={() => { setFileTreeContextMenu(null); fetchWorkspaceFiles() }}>刷新文件树</button>
            <div className="context-menu-divider" />
            <button className="context-menu-item" onClick={() => { setFileTreeContextMenu(null); setRootCreating('file'); setRootCreateValue('') }}>新建文件</button>
            <button className="context-menu-item" onClick={() => { setFileTreeContextMenu(null); setRootCreating('folder'); setRootCreateValue('') }}>新建文件夹</button>
          </div>
        </>
      )}

      <div className="pane-resizer" onMouseDown={(e) => { e.preventDefault(); setResizing('left') }} />

      <div className="course-chat-right">
        <div className="chat-panel" style={{ display: pdfView.active ? 'none' : 'flex' }}>
          <div className="topbar project-editor-topbar">
            <div className="project-window-tabs">
              {chatTabs.map(thread => (
                <div
                  key={thread.id}
                  role="button"
                  tabIndex={0}
                  className={`project-window-tab chat-tab${thread.id === currentThreadId ? ' active' : ''}`}
                  onClick={() => {
                    if (thread.id !== currentThreadId) onOpenThread?.(thread.id)
                  }}
                  onKeyDown={e => {
                    if ((e.key === 'Enter' || e.key === ' ') && thread.id !== currentThreadId) {
                      e.preventDefault()
                      onOpenThread?.(thread.id)
                    }
                  }}
                  title={thread.title || '新对话'}
                >
                  <span>{thread.title || '新对话'}</span>
                  <button
                    type="button"
                    className="project-window-tab-close"
                    onClick={(e) => closeChatTab(thread.id, e)}
                    title="关闭对话"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <div className="topbar-spacer" />
            <span className={`topbar-status ${loading ? 'loading' : ''}`}>
              {loading ? '生成中…' : lastLatency ? `${lastLatency} ms` : 'ready'}
            </span>
          </div>

          <div className="chat-area project-chat-scroll">
            {messages.length === 0 && (
              <div className="chat-empty">
                <div className="chat-empty-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="22" height="22" strokeWidth="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                </div>
                <p>在项目文件树中点击文件可在 VS Code 中打开；下方终端可直接执行命令</p>
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
                {hasInlineContext && (
                  <div className="composer-context-chips">
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
                    {attachedFiles.map(item => (
                      <button
                        key={item.id}
                        type="button"
                        className="composer-context-chip attached-file"
                        onClick={() => removeAttachedFile(item.id)}
                        title={`${item.path || item.name} · 点击移除`}
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
                  <div className="composer-attach-picker">
                    <button
                      className="composer-icon-btn"
                      title="从项目文件中添加"
                      onClick={() => { setShowFilePicker(v => !v); if (showFilePicker) setFilePickerSelected(new Set()) }}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="15" height="15"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
                    </button>
                    {showFilePicker && (
                      <>
                        <div className="context-menu-backdrop" onClick={() => { setShowFilePicker(false); setFilePickerSelected(new Set()) }} onContextMenu={e => { e.preventDefault(); setShowFilePicker(false); setFilePickerSelected(new Set()) }} />
                        <div className="attach-picker-popover" style={{ zIndex: 1000 }}>
                          <div className="attach-picker-head">
                            <strong>选择文件</strong>
                            <button onClick={() => { setShowFilePicker(false); setFilePickerSelected(new Set()) }}>取消</button>
                          </div>
                          <div className="attach-picker-list">
                            {workspaceTree.map(item => (
                              <AttachTreeNode
                                key={`${item.type}:${item.path}`}
                                item={item}
                                selectedPaths={filePickerSelected}
                                toggleAttach={toggleFilePickerSelect}
                              />
                            ))}
                          </div>
                          <div className="attach-picker-foot">
                            <span>{filePickerSelected.size > 0 ? `已选 ${filePickerSelected.size} 个文件` : '未选择文件'}</span>
                            <button onClick={confirmFileAttach} disabled={filePickerSelected.size === 0}>确定</button>
                          </div>
                        </div>
                      </>
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
        {pdfView.active && (
          <PdfErrorBoundary onClose={closePdfInline}>
            <PdfViewer
              url={pdfView.url}
              documentId={pdfView.docId}
              backendUrl={backendUrl}
              userId={userId}
              initialPage={pdfView.initialPage}
              threadId={pdfView.threadId}
              onClose={closePdfInline}
              style={{ display: 'flex' }}
            />
          </PdfErrorBoundary>
        )}
      </div>

      {previewDocId && previewMaterial?.file_type !== 'pdf' && (
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

class PdfErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="pdf-inline-viewer" style={{ display: 'flex', flex: 1, flexDirection: 'column', overflow: 'hidden', background: '#fafbfc' }}>
          <div className="pdf-inline-toolbar">
            <span className="pdf-inline-page-info">PDF 查看器</span>
            <button className="pdf-inline-close-btn" onClick={this.props.onClose} title="关闭">×</button>
          </div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 40 }}>
            <p style={{ color: 'var(--text-error, #d73a49)', fontWeight: 600 }}>PDF 组件渲染错误</p>
            <pre style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxWidth: '100%' }}>{this.state.error?.stack || this.state.error?.message || String(this.state.error)}</pre>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
