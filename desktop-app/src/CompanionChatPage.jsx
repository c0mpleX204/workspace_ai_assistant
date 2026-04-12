import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { chatApi, companionChatApi, companionTaskPollApi } from './api'
import Live2DViewer from './Live2DViewer'

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = e => resolve(e.target.result)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function Message({ m }) {
  return (
    <div className={`msg-row ${m.role}`}>
      <div className="msg-meta">{m.role === 'user' ? '你' : 'AI'}</div>
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

export default function CompanionChatPage({ backendUrl, userId, sessionId, selectedAudioInput, selectedAudioOutput, live2dBgUrl, showToast }) {
  const preferLocalTts = false
  const STT_SLICE_MS = 500
  const MIC_GATE_OPEN_LEVEL = 30
  const MIC_GATE_CLOSE_LEVEL = 20
  const MIC_GATE_HOLD_MS = 900
  const UTTERANCE_SILENCE_FLUSH_MS = 780
  const UTTERANCE_MIN_MS = 320
  const UTTERANCE_MAX_MS = 2300
  const STT_TRANSCRIPT_MERGE_PAUSE_MS = 900
  const STT_TRANSCRIPT_MAX_BUFFER_MS = 4200
  const STT_QUEUE_MAX = 6
  const WS_PCM_TARGET_SAMPLE_RATE = 16000
  const WS_PCM_PROCESSOR_BUFFER_SIZE = 2048
  const COMPANION_HISTORY_SEND_MAX = 16
  const COMPANION_VISIBLE_MESSAGES_MAX = 100
  const companionHistoryStorageKey = useMemo(
    () => `companion_chat_history_v1:${userId || 'user1'}:${sessionId || 'default'}`,
    [userId, sessionId],
  )
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [pendingImages, setPendingImages] = useState([])
  const [isDragging, setIsDragging] = useState(false)
  const [micEnabled, setMicEnabled] = useState(false)
  const [micLevel, setMicLevel] = useState(0)
  const [speechStatus, setSpeechStatus] = useState('idle')
  const [logs, setLogs] = useState([])
  const [routeMode, setRouteMode] = useState('auto')

  const chatAreaRef = useRef(null)
  const textareaRef = useRef(null)
  const composerRef = useRef(null)

  const streamRef = useRef(null)
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const rafRef = useRef(null)
  const volumeAvgRef = useRef(0)
  const voiceActiveRef = useRef(false)
  const voiceHoldUntilRef = useRef(0)
  const voiceGateLoggedStateRef = useRef(false)
  const slicePeakLevelRef = useRef(0)
  const utteranceChunksRef = useRef([])
  const utteranceStartedAtRef = useRef(0)
  const utteranceLastVoiceAtRef = useRef(0)
  const utterancePeakRef = useRef(0)
  const inputMuteUntilRef = useRef(0)
  const mediaRecorderRef = useRef(null)
  const mediaRecorderSliceTimerRef = useRef(null)
  const recorderStartedLoggedRef = useRef(false)
  const sttBusyRef = useRef(false)
  const sttFailCountRef = useRef(0)
  const sttQueueRef = useRef([])
  const sttQueueWorkingRef = useRef(false)
  const sttBackoffUntilRef = useRef(0)
  const useBackendSttRef = useRef(true)
  const sttSocketRef = useRef(null)
  const sttSocketReadyRef = useRef(false)
  const sttSocketIntentionalCloseRef = useRef(false)
  const sttSocketFlushResolverRef = useRef(null)
  const sttSocketPausedRef = useRef(false)
  const sttTranscriptBufferRef = useRef('')
  const sttTranscriptBufferStartedAtRef = useRef(0)
  const sttTranscriptMergeTimerRef = useRef(null)
  const micSourceRef = useRef(null)
  const pcmProcessorRef = useRef(null)
  const pcmMuteNodeRef = useRef(null)

  const chatQueueRef = useRef([])
  const chatBusyRef = useRef(false)
  const delegatedTaskIdRef = useRef('')
  const delegatedPollTimerRef = useRef(null)
  const delegatedPollBusyRef = useRef(false)

  const ttsQueueRef = useRef([])
  const ttsPlayingRef = useRef(false)

  function inferAudioExt(mimeType) {
    const t = String(mimeType || '').toLowerCase()
    if (t.includes('webm')) return 'webm'
    if (t.includes('ogg')) return 'ogg'
    if (t.includes('mp4') || t.includes('mpeg')) return 'mp4'
    if (t.includes('wav')) return 'wav'
    return 'webm'
  }

  function repairMojibakeText(text) {
    const raw = String(text || '')
    if (!raw) return raw

    const hasC1 = /[\u0080-\u009F]/.test(raw)
    const suspicious = /(Ã|Â|â|ð|ï|å|ä|æ|ç|�|é|è¦|é¢|è¯|ã)/.test(raw)
    if (!hasC1 && !suspicious) return raw

    try {
      const fixed = decodeURIComponent(escape(raw))
      if (fixed) return fixed
    } catch (e) { void e }
    return raw
  }

  function clearSttTranscriptMergeTimer() {
    if (sttTranscriptMergeTimerRef.current) {
      clearTimeout(sttTranscriptMergeTimerRef.current)
      sttTranscriptMergeTimerRef.current = null
    }
  }

  function flushMergedSttTranscript(reason = 'pause') {
    const merged = String(sttTranscriptBufferRef.current || '').trim()
    clearSttTranscriptMergeTimer()
    sttTranscriptBufferRef.current = ''
    sttTranscriptBufferStartedAtRef.current = 0
    if (!merged) return
    pushLog('speech', `合并语音(${reason}): ${merged}`)
    enqueueMessage(merged, [], 'stt')
  }

  function appendSttTranscriptChunk(text) {
    const chunk = String(text || '').trim()
    if (!chunk) return

    const now = Date.now()
    const previous = String(sttTranscriptBufferRef.current || '').trim()
    if (!previous) {
      sttTranscriptBufferRef.current = chunk
      sttTranscriptBufferStartedAtRef.current = now
    } else {
      const needSpace = /[A-Za-z0-9]$/.test(previous) && /^[A-Za-z0-9]/.test(chunk)
      sttTranscriptBufferRef.current = `${previous}${needSpace ? ' ' : ''}${chunk}`
    }

    if (
      sttTranscriptBufferStartedAtRef.current > 0 &&
      now - sttTranscriptBufferStartedAtRef.current >= STT_TRANSCRIPT_MAX_BUFFER_MS
    ) {
      flushMergedSttTranscript('max_window')
      return
    }

    clearSttTranscriptMergeTimer()
    sttTranscriptMergeTimerRef.current = setTimeout(() => {
      flushMergedSttTranscript('silence')
    }, STT_TRANSCRIPT_MERGE_PAUSE_MS)
  }

  useEffect(() => {
    const el = chatAreaRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages, loading])

  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px'
  }, [input])

  const canSend = useMemo(() => (input.trim() || pendingImages.length > 0) && !loading, [input, pendingImages, loading])
  const visibleMessages = useMemo(
    () => messages.slice(-COMPANION_VISIBLE_MESSAGES_MAX),
    [messages],
  )
  const pushLog = useCallback((type, text) => {
    setLogs(prev => [...prev.slice(-149), { type, text, ts: new Date().toLocaleTimeString() }])
  }, [])

  useEffect(() => {
    try {
      const raw = localStorage.getItem(companionHistoryStorageKey)
      if (!raw) {
        setMessages([])
        return
      }
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) {
        setMessages([])
        return
      }
      const sanitized = parsed
        .filter(x => x && (x.role === 'user' || x.role === 'assistant'))
        .map(x => ({
          ...x,
          role: x.role,
          content: String(x.content || ''),
          streaming: false,
        }))
      setMessages(sanitized)
    } catch (e) {
      void e
      setMessages([])
    }
  }, [companionHistoryStorageKey])

  useEffect(() => {
    try {
      localStorage.setItem(companionHistoryStorageKey, JSON.stringify(messages))
    } catch (e) {
      // If quota is hit, keep newer messages first.
      try {
        const trimmed = messages.slice(-Math.max(200, Math.floor(messages.length * 0.7)))
        localStorage.setItem(companionHistoryStorageKey, JSON.stringify(trimmed))
      } catch (inner) {
        void inner
      }
      void e
    }
  }, [messages, companionHistoryStorageKey])

  useEffect(() => {
    const isEditableTarget = (target) => {
      if (!target || !(target instanceof Element)) return false
      if (target.closest('textarea, input, select')) return true
      const editable = target.closest('[contenteditable]')
      if (!editable) return false
      const value = editable.getAttribute('contenteditable')
      return value !== 'false'
    }

    const onKeyDown = (e) => {
      if (e.defaultPrevented) return
      if (e.repeat) return
      if (e.ctrlKey || e.altKey || e.metaKey) return
      if (String(e.key || '').toLowerCase() !== 'y') return
      if (isEditableTarget(e.target)) return

      e.preventDefault()
      setMicEnabled(prev => {
        const next = !prev
        pushLog('speech', `快捷键 Y: ${next ? 'Mic ON' : 'Mic OFF'}`)
        return next
      })
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [pushLog])

  function buildSttWsUrl() {
    try {
      const parsed = new URL(backendUrl || 'http://127.0.0.1:8000')
      const protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:'
      return `${protocol}//${parsed.host}/stt/ws`
    } catch {
      return 'ws://127.0.0.1:8000/stt/ws'
    }
  }

  function resetRealtimeStt(reason = '') {
    const ws = sttSocketRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN || !sttSocketReadyRef.current) return
    try {
      ws.send('reset')
      void reason
    } catch (e) { void e }
  }

  async function openSttSocket() {
    const ws = sttSocketRef.current
    if (ws && ws.readyState === WebSocket.OPEN && sttSocketReadyRef.current) {
      return true
    }

    return await new Promise(resolve => {
      const url = buildSttWsUrl()
      const socket = new WebSocket(url)
      socket.binaryType = 'arraybuffer'
      sttSocketIntentionalCloseRef.current = false

      let settled = false
      const done = (ok) => {
        if (settled) return
        settled = true
        resolve(ok)
      }

      const timer = setTimeout(() => {
        try { socket.close() } catch (e) { void e }
        done(false)
      }, 8000)

      socket.onopen = () => {
        sttSocketRef.current = socket
      }

      socket.onmessage = ev => {
        let payload
        try {
          payload = JSON.parse(String(ev.data || '{}'))
        } catch {
          return
        }

        if (payload.type === 'ready') {
          clearTimeout(timer)
          sttSocketReadyRef.current = true
          setSpeechStatus('listening')
          pushLog('speech', '实时语音通道已连接')
          done(true)
          return
        }

        if (payload.type === 'flush_complete') {
          const resolver = sttSocketFlushResolverRef.current
          sttSocketFlushResolverRef.current = null
          if (typeof resolver === 'function') resolver()
          return
        }

        if (payload.type === 'transcript') {
          const text = repairMojibakeText(String(payload.text || '').trim())
          if (text) {
            sttFailCountRef.current = 0
            pushLog('speech', `识别文本: ${text}`)
            appendSttTranscriptChunk(text)
          }
          return
        }

        if (payload.type === 'speech_start') {
          clearSttTranscriptMergeTimer()
          setSpeechStatus('listening')
          return
        }

        if (payload.type === 'speech_end') {
          setSpeechStatus('recognizing')
          return
        }

        if (payload.type === 'error') {
          const msg = String(payload.message || '实时语音错误')
          pushLog('error', msg)
        }
      }

      socket.onerror = () => {
        clearTimeout(timer)
        done(false)
      }

      socket.onclose = () => {
        const intentional = sttSocketIntentionalCloseRef.current
        sttSocketRef.current = null
        sttSocketReadyRef.current = false
        const resolver = sttSocketFlushResolverRef.current
        sttSocketFlushResolverRef.current = null
        if (typeof resolver === 'function') resolver()
        clearTimeout(timer)
        if (!intentional) {
          pushLog('error', '实时语音通道已断开，自动回退HTTP识别')
        }
        done(false)
      }
    })
  }

  async function closeSttSocket(options = {}) {
    const flushFirst = !!options.flushFirst
    const ws = sttSocketRef.current
    if (!ws) return

    if (flushFirst && ws.readyState === WebSocket.OPEN) {
      try {
        await new Promise(resolve => {
          sttSocketFlushResolverRef.current = resolve
          ws.send('flush')
          setTimeout(resolve, 700)
        })
      } catch (e) { void e }
    }

    sttSocketIntentionalCloseRef.current = true
    try { ws.close() } catch (e) { void e }
    sttSocketRef.current = null
    sttSocketReadyRef.current = false
  }

  function downsampleFloat32(input, inputRate, outputRate) {
    if (!input || input.length === 0) return new Float32Array(0)
    if (!inputRate || !outputRate || inputRate === outputRate) return new Float32Array(input)

    const ratio = inputRate / outputRate
    const outLength = Math.floor(input.length / ratio)
    if (outLength <= 0) return new Float32Array(0)

    const output = new Float32Array(outLength)
    for (let i = 0; i < outLength; i += 1) {
      const src = i * ratio
      const left = Math.floor(src)
      const right = Math.min(left + 1, input.length - 1)
      const frac = src - left
      output[i] = input[left] * (1 - frac) + input[right] * frac
    }
    return output
  }

  function float32ToInt16(input) {
    if (!input || input.length === 0) return new Int16Array(0)
    const out = new Int16Array(input.length)
    for (let i = 0; i < input.length; i += 1) {
      const s = Math.max(-1, Math.min(1, input[i]))
      out[i] = s < 0 ? Math.round(s * 32768) : Math.round(s * 32767)
    }
    return out
  }

  function stopRealtimePcmStreaming() {
    if (pcmProcessorRef.current) {
      try { pcmProcessorRef.current.onaudioprocess = null } catch (e) { void e }
      try { pcmProcessorRef.current.disconnect() } catch (e) { void e }
    }
    if (pcmMuteNodeRef.current) {
      try { pcmMuteNodeRef.current.disconnect() } catch (e) { void e }
    }
    pcmProcessorRef.current = null
    pcmMuteNodeRef.current = null
    sttSocketPausedRef.current = false
  }

  function startRealtimePcmStreaming(sourceNode, audioContext) {
    if (!sourceNode || !audioContext) return false
    if (typeof audioContext.createScriptProcessor !== 'function') return false

    stopRealtimePcmStreaming()

    const processor = audioContext.createScriptProcessor(WS_PCM_PROCESSOR_BUFFER_SIZE, 1, 1)
    const mute = audioContext.createGain()
    mute.gain.value = 0

    processor.onaudioprocess = (event) => {
      const ws = sttSocketRef.current
      if (!ws || ws.readyState !== WebSocket.OPEN || !sttSocketReadyRef.current) return

      const shouldPause = Date.now() < inputMuteUntilRef.current || ttsPlayingRef.current || chatBusyRef.current
      if (shouldPause) {
        if (!sttSocketPausedRef.current) {
          sttSocketPausedRef.current = true
          resetRealtimeStt('busy_or_tts')
        }
        return
      }

      if (sttSocketPausedRef.current) {
        sttSocketPausedRef.current = false
      }

      const input = event.inputBuffer.getChannelData(0)
      const downsampled = downsampleFloat32(
        input,
        Number(audioContext.sampleRate || WS_PCM_TARGET_SAMPLE_RATE),
        WS_PCM_TARGET_SAMPLE_RATE,
      )
      const pcm = float32ToInt16(downsampled)
      if (!pcm || pcm.length < 160) return

      try {
        ws.send(pcm.buffer)
      } catch (e) { void e }
    }

    try {
      sourceNode.connect(processor)
      processor.connect(mute)
      mute.connect(audioContext.destination)
    } catch (e) {
      stopRealtimePcmStreaming()
      return false
    }

    pcmProcessorRef.current = processor
    pcmMuteNodeRef.current = mute
    return true
  }

  async function checkBackendHealth() {
    try {
      const res = await fetch(backendUrl + '/health', { method: 'GET' })
      return !!res.ok
    } catch {
      return false
    }
  }

  function resetUtteranceBuffer() {
    utteranceChunksRef.current = []
    utteranceStartedAtRef.current = 0
    utteranceLastVoiceAtRef.current = 0
    utterancePeakRef.current = 0
  }

  function flushUtteranceToQueue(reason = 'silence') {
    const chunks = utteranceChunksRef.current
    if (!chunks || chunks.length === 0) return

    const started = utteranceStartedAtRef.current || Date.now()
    const durationMs = Math.max(0, Date.now() - started)
    const mimeType = chunks[0]?.type || 'audio/webm'
    const blob = new Blob(chunks, { type: mimeType })
    const peak = utterancePeakRef.current
    resetUtteranceBuffer()

    if (durationMs < UTTERANCE_MIN_MS || blob.size < 2048) {
      return
    }

    // Drop weak low-energy clips to reduce noise hallucinations.
    if (peak < MIC_GATE_OPEN_LEVEL + 3) {
      return
    }

    if (sttQueueRef.current.length >= STT_QUEUE_MAX) {
      sttQueueRef.current.shift()
      pushLog('error', '语音队列已满，已丢弃最旧句段')
    }

    sttQueueRef.current.push({
      blob,
      retries: 0,
      ext: inferAudioExt(mimeType),
    })
    processSttQueue()

    if (reason === 'max') {
      pushLog('speech', '长语音已自动分段提交')
    }
  }

  function startBackendRecorder(stream) {
    if (!stream) return false

    let recorder
    try { recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' }) }
    catch (e) { void e; recorder = new MediaRecorder(stream) }

    recorder.onstart = () => {
      setSpeechStatus('listening')
      if (!recorderStartedLoggedRef.current) {
        recorderStartedLoggedRef.current = true
        pushLog('speech', `语音切片监听已开启（后端STT，${STT_SLICE_MS}ms/片）`)
      }
    }
    recorder.ondataavailable = e => {
      if (!micEnabled) return
      if (!e?.data) return
      enqueueSttChunk(e.data, slicePeakLevelRef.current)
      slicePeakLevelRef.current = 0
    }
    recorder.onstop = () => {
      if (!micEnabled || !useBackendSttRef.current) return
      try { recorder.start() } catch (e) { void e }
    }
    recorder.onerror = e => { pushLog('error', '录音器错误: ' + (e?.error?.message || 'unknown')); setSpeechStatus('error') }

    mediaRecorderRef.current = recorder
    try { recorder.start() } catch (e) { void e; return false }
    if (mediaRecorderSliceTimerRef.current) {
      clearInterval(mediaRecorderSliceTimerRef.current)
      mediaRecorderSliceTimerRef.current = null
    }
    mediaRecorderSliceTimerRef.current = setInterval(() => {
      if (!micEnabled || !useBackendSttRef.current) return
      const mr = mediaRecorderRef.current
      if (!mr || mr.state !== 'recording') return
      try { mr.stop() } catch (e) { void e }
    }, STT_SLICE_MS)
    return true
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

  async function consumeTtsQueue() {
    if (ttsPlayingRef.current) return
    const url = ttsQueueRef.current.shift()
    if (!url) return

    ttsPlayingRef.current = true
    const audio = new Audio(url)
    inputMuteUntilRef.current = Date.now() + 2200
    resetRealtimeStt('tts_playing')
    if (selectedAudioOutput && typeof audio.setSinkId === 'function') {
      try { await audio.setSinkId(selectedAudioOutput) } catch (e) { void e }
    }

    const done = () => {
      URL.revokeObjectURL(url)
      ttsPlayingRef.current = false
      consumeTtsQueue()
    }
    audio.onended = done
    audio.onerror = done
    audio.play().catch(done)
  }

  async function speak(text) {
    if (!text) return
    if (preferLocalTts) {
      const synth = window.speechSynthesis
      if (!synth) {
        pushLog('error', '当前环境不支持本地语音播报')
        return
      }

      const utter = new SpeechSynthesisUtterance(text.slice(0, 600))
      utter.lang = 'zh-CN'
      utter.rate = 1.0
      utter.pitch = 1.0
      synth.speak(utter)
      return
    }

    try {
      const res = await fetch(backendUrl + '/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.slice(0, 600) }),
      })
      if (!res.ok) throw new Error(await res.text())
      ttsQueueRef.current.push(URL.createObjectURL(await res.blob()))
      consumeTtsQueue()
    } catch (e) {
      pushLog('error', 'TTS失败: ' + e.message)
    }
  }

  function stopDelegatedTaskPolling() {
    if (delegatedPollTimerRef.current) {
      clearInterval(delegatedPollTimerRef.current)
      delegatedPollTimerRef.current = null
    }
    delegatedPollBusyRef.current = false
  }

  async function handleDelegatedTaskFinished(task) {
    const status = String(task?.status || '').toLowerCase()
    const ok = status === 'completed' && task?.ok !== false
    const summary = repairMojibakeText(String(task?.summary || '').trim())
    const raw = repairMojibakeText(String(task?.main_result || '').trim())

    const notifyText = ok
      ? '我回来了，后台任务处理完成。我先给你结论，原始输出也放在下面。'
      : '后台任务这次没跑成功，我把结果和原始输出贴给你，我们一起修一下。'

    setMessages(prev => [
      ...prev,
      {
        role: 'assistant',
        content: notifyText,
        delegatedResult: {
          summary,
          raw,
        },
      },
    ])

    pushLog('output', `${ok ? '后台任务完成' : '后台任务失败'}: ${(summary || raw || '无返回').slice(0, 80)}`)
    await speak(summary || notifyText)
  }

  async function pollDelegatedTaskOnce() {
    if (delegatedPollBusyRef.current) return
    if (!delegatedTaskIdRef.current) return

    delegatedPollBusyRef.current = true
    try {
      const resp = await companionTaskPollApi(
        backendUrl,
        {
          user_id: userId,
          session_id: `companion_${sessionId}`,
          task_id: delegatedTaskIdRef.current,
        },
        { timeoutMs: 6000 },
      )

      const task = resp?.task
      if (!task || String(task.task_id || '') !== delegatedTaskIdRef.current) return

      const status = String(task.status || '').toLowerCase()
      if (status === 'completed' || status === 'failed') {
        delegatedTaskIdRef.current = ''
        stopDelegatedTaskPolling()
        await handleDelegatedTaskFinished(task)
      }
    } catch (e) {
      pushLog('error', '后台任务轮询失败: ' + String(e?.message || e || 'unknown'))
    } finally {
      delegatedPollBusyRef.current = false
    }
  }

  function startDelegatedTaskPolling(taskId) {
    const id = String(taskId || '').trim()
    if (!id) return
    delegatedTaskIdRef.current = id
    stopDelegatedTaskPolling()
    delegatedPollTimerRef.current = setInterval(() => {
      pollDelegatedTaskOnce()
    }, 1800)
    pollDelegatedTaskOnce()
  }

  async function sendMessageNow(text, images = []) {
    const content = (text || '').trim()
    if (!content && images.length === 0) return

    setMessages(m => [...m, { role: 'user', content, images }, { role: 'assistant', content: '', streaming: true }])
    setLoading(true)
    resetRealtimeStt('chat_replying')
    pushLog('input', content || '[图片消息]')

    try {
      const historyMessages = (messages || [])
        .filter(m => (m.role === 'user' || m.role === 'assistant') && !m.streaming)
        .map(m => ({ role: m.role, content: String(m.content || '').trim() }))
        .filter(m => m.content)
        .slice(-COMPANION_HISTORY_SEND_MAX)

      const currentUserContent = content || '请分析这张图片'
      const apiMessages = [...historyMessages, { role: 'user', content: currentUserContent }]

      const payload = {
        user_id: userId,
        session_id: `companion_${sessionId}`,
        messages: apiMessages,
        scene: 'desktop',
        route_mode: routeMode,
        capability_ide: false,
      }
      if (images.length > 0) payload.image_url = images[0]

      const applyAssistantText = (nextText, done = false) => {
        setMessages(prev => {
          const list = [...prev]
          for (let i = list.length - 1; i >= 0; i -= 1) {
            if (list[i].role === 'assistant' && list[i].streaming) {
              list[i] = { ...list[i], content: nextText, streaming: !done }
              return list
            }
          }
          return [...list, { role: 'assistant', content: nextText, streaming: !done }]
        })
      }

      try {
        const resp = await companionChatApi(backendUrl, payload, { timeoutMs: 22000 })
        const reply = repairMojibakeText(resp?.reply || '')
        const ttsText = repairMojibakeText(resp?.tts_text || reply || '')
        const delegatedTaskId = String(resp?.delegated_task?.task_id || '').trim()
        applyAssistantText(reply, true)
        pushLog('output', reply.slice(0, 80))
        if (delegatedTaskId) {
          pushLog('speech', `后台任务已启动: ${delegatedTaskId.slice(0, 8)}...`)
          startDelegatedTaskPolling(delegatedTaskId)
        }
        if (resp?.emotion) {
          pushLog('speech', `情绪: ${resp.emotion}`)
        }
        if (Array.isArray(resp?.action_intents) && resp.action_intents.length > 0) {
          pushLog('speech', `动作意图: ${resp.action_intents.length} 条`)
        }
        await speak(ttsText)
      } catch (companionErr) {
        pushLog('error', '陪伴接口失败，已自动回退普通请求: ' + String(companionErr?.message || companionErr || 'unknown'))
        const resp = await chatApi(backendUrl, payload, { timeoutMs: 22000 })
        const reply = repairMojibakeText(resp.reply || '')
        applyAssistantText(reply, true)
        pushLog('output', reply.slice(0, 80))
        await speak(reply)
      }
    } catch (e) {
      const err = '请求失败: ' + (e?.message || e)
      setMessages(prev => {
        const list = [...prev]
        for (let i = list.length - 1; i >= 0; i -= 1) {
          if (list[i].role === 'assistant' && list[i].streaming) {
            list[i] = { ...list[i], content: err, streaming: false }
            return list
          }
        }
        return [...list, { role: 'assistant', content: err }]
      })
      pushLog('error', err)
    } finally {
      setLoading(false)
    }
  }

  async function drainChatQueue() {
    if (chatBusyRef.current) return
    chatBusyRef.current = true
    try {
      while (chatQueueRef.current.length > 0) {
        const item = chatQueueRef.current.shift()
        await sendMessageNow(item.text, item.images)
      }
    } finally {
      chatBusyRef.current = false
    }
  }

  function enqueueMessage(text, images = [], source = 'manual') {
    if (source === 'stt' && (chatBusyRef.current || chatQueueRef.current.length > 0)) {
      chatQueueRef.current = [{ text, images }]
      pushLog('speech', 'AI处理中：已保留最新一句语音，丢弃旧待发队列')
      return
    }
    chatQueueRef.current.push({ text, images })
    drainChatQueue()
  }

  function handleSend() {
    const images = [...pendingImages]
    const text = input
    setInput('')
    setPendingImages([])
    enqueueMessage(text, images)
  }

  function enqueueSttChunk(blob, peakLevel = 0) {
    if (!useBackendSttRef.current) return
    if (!blob || blob.size < 1024) return
    if (Date.now() < inputMuteUntilRef.current || ttsPlayingRef.current || loading || chatBusyRef.current) {
      resetRealtimeStt('busy_or_tts')
      return
    }

    const now = Date.now()
    const voiceTriggered = voiceActiveRef.current || peakLevel >= MIC_GATE_OPEN_LEVEL
    if (voiceTriggered) {
      if (!utteranceStartedAtRef.current && peakLevel < MIC_GATE_OPEN_LEVEL + 2) {
        return
      }
      if (!utteranceStartedAtRef.current) {
        utteranceStartedAtRef.current = now
      }
      utteranceLastVoiceAtRef.current = now
      utterancePeakRef.current = Math.max(utterancePeakRef.current, peakLevel || 0)
      utteranceChunksRef.current.push(blob)

      if (now - utteranceStartedAtRef.current >= UTTERANCE_MAX_MS) {
        flushUtteranceToQueue('max')
      }
      return
    }

    if (
      utteranceChunksRef.current.length > 0 &&
      utteranceLastVoiceAtRef.current > 0 &&
      now - utteranceLastVoiceAtRef.current >= UTTERANCE_SILENCE_FLUSH_MS
    ) {
      flushUtteranceToQueue('silence')
    }
  }

  async function sendChunkToStt(item) {
    if (!item?.blob || item.blob.size < 1024 || sttBusyRef.current) return
    sttBusyRef.current = true
    setSpeechStatus('recognizing')
    try {
      const ws = sttSocketRef.current
      if (ws && ws.readyState === WebSocket.OPEN && sttSocketReadyRef.current) {
        const buf = await item.blob.arrayBuffer()
        ws.send(buf)
        sttFailCountRef.current = 0
        setSpeechStatus('listening')
        return
      }

      const form = new FormData()
      form.append('file', item.blob, `slice-${Date.now()}.${item.ext || 'webm'}`)
      const res = await fetch(backendUrl + '/stt', { method: 'POST', body: form })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const text = repairMojibakeText((data.text || '').trim())
      sttFailCountRef.current = 0
      if (text) {
        pushLog('speech', `识别文本: ${text}`)
        appendSttTranscriptChunk(text)
      }
      setSpeechStatus('listening')
    } catch (e) {
      sttFailCountRef.current += 1
      item.retries = (item.retries || 0) + 1
      if (useBackendSttRef.current && item.retries <= 2) {
        sttBackoffUntilRef.current = Date.now() + 1000 * item.retries
        sttQueueRef.current.unshift(item)
        setSpeechStatus('listening')
      } else if (useBackendSttRef.current && sttFailCountRef.current >= 3) {
        sttBackoffUntilRef.current = Date.now() + 6000
        sttFailCountRef.current = 0
        pushLog('error', '语音识别连续失败，队列暂停6秒后自动恢复')
        setSpeechStatus('error')
      } else {
        setSpeechStatus('listening')
      }
      const errText = String(e?.message || e || '').replace(/\s+/g, ' ').slice(0, 160)
      pushLog('error', '语音识别错误: ' + errText)
    } finally {
      sttBusyRef.current = false
    }
  }

  async function processSttQueue() {
    if (sttQueueWorkingRef.current) return
    sttQueueWorkingRef.current = true

    try {
      while (useBackendSttRef.current && sttQueueRef.current.length > 0) {
        if (chatBusyRef.current || ttsPlayingRef.current || Date.now() < inputMuteUntilRef.current) {
          await new Promise(resolve => setTimeout(resolve, 120))
          continue
        }
        const waitMs = sttBackoffUntilRef.current - Date.now()
        if (waitMs > 0) {
          await new Promise(resolve => setTimeout(resolve, Math.min(waitMs, 500)))
          continue
        }

        const item = sttQueueRef.current.shift()
        if (!item) continue
        await sendChunkToStt(item)
      }
    } finally {
      sttQueueWorkingRef.current = false
    }
  }

  function stopMic() {
    flushMergedSttTranscript('stop_mic')
    if (mediaRecorderSliceTimerRef.current) {
      clearInterval(mediaRecorderSliceTimerRef.current)
      mediaRecorderSliceTimerRef.current = null
    }
    const mr = mediaRecorderRef.current
    if (mr && mr.state !== 'inactive') {
      try { mr.stop() } catch (e) { void e }
    }
    mediaRecorderRef.current = null
    stopRealtimePcmStreaming()
    if (micSourceRef.current) {
      try { micSourceRef.current.disconnect() } catch (e) { void e }
    }
    micSourceRef.current = null
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop())
    streamRef.current = null
    if (audioContextRef.current) audioContextRef.current.close().catch(() => {})
    audioContextRef.current = null
    void closeSttSocket({ flushFirst: true })
    analyserRef.current = null
    sttQueueRef.current = []
    sttQueueWorkingRef.current = false
    sttBackoffUntilRef.current = 0
    sttFailCountRef.current = 0
    recorderStartedLoggedRef.current = false
    inputMuteUntilRef.current = 0
    resetUtteranceBuffer()
    useBackendSttRef.current = true
    if (window.speechSynthesis) {
      try { window.speechSynthesis.cancel() } catch (e) { void e }
    }
    volumeAvgRef.current = 0
    voiceActiveRef.current = false
    voiceHoldUntilRef.current = 0
    voiceGateLoggedStateRef.current = false
    slicePeakLevelRef.current = 0
    setMicLevel(0)
    setSpeechStatus('idle')
  }

  async function startMic() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          ...(selectedAudioInput ? { deviceId: { exact: selectedAudioInput } } : {}),
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      streamRef.current = stream

      const ac = new (window.AudioContext || window.webkitAudioContext)()
      audioContextRef.current = ac
      const analyser = ac.createAnalyser()
      analyser.fftSize = 256
      const sourceNode = ac.createMediaStreamSource(stream)
      micSourceRef.current = sourceNode
      sourceNode.connect(analyser)
      analyserRef.current = analyser

      const arr = new Uint8Array(analyser.frequencyBinCount)
      const loop = () => {
        if (!analyserRef.current) return
        analyserRef.current.getByteFrequencyData(arr)
        const avg = arr.reduce((a, b) => a + b, 0) / arr.length
        const level = Math.min(100, Math.round(avg * 1.6))
        const now = Date.now()

        if (level >= MIC_GATE_OPEN_LEVEL) {
          voiceActiveRef.current = true
          voiceHoldUntilRef.current = now + MIC_GATE_HOLD_MS
        } else if (voiceActiveRef.current && level <= MIC_GATE_CLOSE_LEVEL && now > voiceHoldUntilRef.current) {
          voiceActiveRef.current = false
        }

        if (voiceActiveRef.current !== voiceGateLoggedStateRef.current) {
          voiceGateLoggedStateRef.current = voiceActiveRef.current
          if (voiceActiveRef.current) {
            pushLog('speech', `检测到语音输入（音量阈值>${MIC_GATE_OPEN_LEVEL}）`)
          } else {
            flushUtteranceToQueue('silence')
          }
        }

        volumeAvgRef.current = avg
        slicePeakLevelRef.current = Math.max(slicePeakLevelRef.current, level)
        setMicLevel(level)
        rafRef.current = requestAnimationFrame(loop)
      }
      loop()

      const backendOk = await checkBackendHealth()
      if (!backendOk) {
        pushLog('error', '后端STT不可用，请先启动后端服务')
        setSpeechStatus('error')
        return
      }

      const wsOk = await openSttSocket()
      if (!wsOk) {
        pushLog('error', '实时语音通道不可用，已回退HTTP识别')
        useBackendSttRef.current = true
        startBackendRecorder(stream)
        return
      }

      const pcmOk = startRealtimePcmStreaming(sourceNode, ac)
      if (!pcmOk) {
        pushLog('error', '实时PCM采集不可用，已回退HTTP识别')
        useBackendSttRef.current = true
        startBackendRecorder(stream)
        return
      }

      useBackendSttRef.current = false
      setSpeechStatus('listening')
    } catch (e) {
      showToast('麦克风启动失败: ' + e.message, 'error')
      pushLog('error', '麦克风启动失败: ' + e.message)
      stopMic()
    }
  }

  useEffect(() => {
    if (micEnabled) startMic()
    else stopMic()
    return () => stopMic()
  }, [micEnabled, selectedAudioInput])

  useEffect(() => {
    return () => {
      stopDelegatedTaskPolling()
      clearSttTranscriptMergeTimer()
    }
  }, [])

  return (
    <div className="companion-layout">
      <div className="companion-left">
        <div className="companion-card companion-chat-card">
          <div className="companion-card-head">
            <div>
              <div className="companion-title">持续对话</div>
              <div className="companion-subtitle">本地语音识别 + 本地优先语音播报</div>
            </div>
            <div className="companion-head-controls">
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
                <div className="chat-empty-icon">🗣️</div>
                <p>打开麦克风即可持续语音对话</p>
              </div>
            )}

            {visibleMessages.map((m, i) => (
              <Message key={i} m={m} />
            ))}

            {loading && !messages.some(m => m.streaming) && (
              <div className="msg-row assistant">
                <div className="msg-meta">AI</div>
                <div className="typing-indicator">
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                </div>
              </div>
            )}
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
              for (const f of Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'))) {
                await addImageFile(f)
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

      <div className="companion-right-stack">
        <div className="companion-right companion-top">
          <div className="companion-card monitor-card">
            <div className="monitor-title">后台检测日志</div>
            <div className="monitor-list">
              {logs.length === 0 && <div className="monitor-empty">暂无日志</div>}
              {logs.map((x, i) => (
                <div key={i} className={`monitor-item ${x.type}`}>
                  <span className="monitor-time">[{x.ts}]</span>
                  <span className="monitor-text">{x.text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="companion-right companion-bottom">
          <div className="companion-card" style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
            <Live2DViewer backgroundImageUrl={live2dBgUrl} />
          </div>
        </div>
      </div>
    </div>
  )
}
