export const getBackend = (baseUrl) => baseUrl || (window.env && window.env.BACKEND_URL) || 'http://127.0.0.1:8000'

export async function getProviderSettingsApi(baseUrl) {
  const url = `${getBackend(baseUrl)}/settings/provider`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export async function updateProviderSettingsApi(baseUrl, payload) {
  const url = `${getBackend(baseUrl)}/settings/provider`
  const res = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export async function getChatSessionApi(baseUrl, sessionId, userId = 'default_user') {
  const params = new URLSearchParams()
  if (userId) params.set('user_id', userId)
  const url = `${getBackend(baseUrl)}/chat/sessions/${encodeURIComponent(sessionId)}?${params.toString()}`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export async function chatApi(baseUrl, payload, options = {}) {
  const url = `${getBackend(baseUrl)}/chat`
  const controller = new AbortController()
  const timeoutMs = Number(options?.timeoutMs || 0)
  let timer = null
  if (timeoutMs > 0) {
    timer = setTimeout(() => {
      try { controller.abort() } catch (e) { void e }
    }, timeoutMs)
  }
  let res
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
  } catch (e) {
    if (e?.name === 'AbortError') {
      throw new Error(`chat timeout after ${timeoutMs}ms`)
    }
    throw e
  } finally {
    if (timer) clearTimeout(timer)
  }
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  try { return JSON.parse(text) } catch (e) { return { reply: text } }
}

export async function companionChatApi(baseUrl, payload, options = {}) {
  const url = `${getBackend(baseUrl)}/companion/chat`
  const controller = new AbortController()
  const timeoutMs = Number(options?.timeoutMs || 0)
  let timer = null
  if (timeoutMs > 0) {
    timer = setTimeout(() => {
      try { controller.abort() } catch (e) { void e }
    }, timeoutMs)
  }

  let res
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
  } catch (e) {
    if (e?.name === 'AbortError') {
      throw new Error(`companion chat timeout after ${timeoutMs}ms`)
    }
    throw e
  } finally {
    if (timer) clearTimeout(timer)
  }

  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export async function companionTaskPollApi(baseUrl, payload, options = {}) {
  const url = `${getBackend(baseUrl)}/companion/task/poll`
  const controller = new AbortController()
  const timeoutMs = Number(options?.timeoutMs || 0)
  let timer = null
  if (timeoutMs > 0) {
    timer = setTimeout(() => {
      try { controller.abort() } catch (e) { void e }
    }, timeoutMs)
  }

  let res
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
  } catch (e) {
    if (e?.name === 'AbortError') {
      throw new Error(`companion task poll timeout after ${timeoutMs}ms`)
    }
    throw e
  } finally {
    if (timer) clearTimeout(timer)
  }

  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export async function chatStreamApi(baseUrl, payload, handlers = {}) {
  const url = `${getBackend(baseUrl)}/chat/stream`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: handlers.signal,
  })

  if (!res.ok) {
    const text = await res.text()
    try {
      const j = JSON.parse(text)
      throw new Error(j.detail || JSON.stringify(j))
    } catch (e) {
      if (e.message !== text) throw e
      throw new Error(text || res.statusText)
    }
  }

  if (!res.body) {
    throw new Error('stream body is empty')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let fullText = ''

  const parseEventChunk = (rawChunk) => {
    const lines = rawChunk
      .split('\n')
      .map(x => x.trim())
      .filter(Boolean)
      .filter(x => x.startsWith('data:'))

    for (const line of lines) {
      const payloadText = line.slice(5).trim()
      if (!payloadText) continue
      let obj
      try {
        obj = JSON.parse(payloadText)
      } catch {
        continue
      }

      if (obj.error) {
        throw new Error(String(obj.error))
      }

      if (obj.delta) {
        fullText += String(obj.delta)
        if (handlers.onDelta) handlers.onDelta(String(obj.delta), fullText)
      }

      if (obj.usage && handlers.onUsage) {
        handlers.onUsage(obj.usage)
      }

      if (obj.status && handlers.onStatus) {
        handlers.onStatus(obj.status)
      }

      if (obj.done) {
        if (obj.reply && !fullText) fullText = String(obj.reply)
        if (handlers.onDone) handlers.onDone(obj)
        return {
          done: true,
          reply: fullText,
          latency_ms: Number(obj.latency_ms || 0),
          usage: obj.usage || null,
          reference: obj.reference || [],
          model: obj.model || '',
        }
      }
    }

    return null
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    let idx
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const end = parseEventChunk(chunk)
      if (end?.done) return end
    }
  }

  if (buffer.trim()) {
    const end = parseEventChunk(buffer)
    if (end?.done) return end
  }

  if (handlers.onDone) handlers.onDone({ done: true, reply: fullText, latency_ms: 0 })
  return { done: true, reply: fullText, latency_ms: 0, usage: null, reference: [], model: '' }
}

export async function agentRunStreamApi(baseUrl, payload, handlers = {}) {
  const url = `${getBackend(baseUrl)}/agent/runs/stream`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: handlers.signal,
  })

  if (!res.ok) {
    const text = await res.text()
    try {
      const j = JSON.parse(text)
      throw new Error(j.detail || JSON.stringify(j))
    } catch (e) {
      if (e.message !== text) throw e
      throw new Error(text || res.statusText)
    }
  }

  if (!res.body) throw new Error('agent run stream body is empty')

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let fullText = ''

  const parseEventChunk = (rawChunk) => {
    const lines = rawChunk
      .split('\n')
      .map(x => x.trim())
      .filter(Boolean)
      .filter(x => x.startsWith('data:'))

    for (const line of lines) {
      const payloadText = line.slice(5).trim()
      if (!payloadText) continue
      let obj
      try {
        obj = JSON.parse(payloadText)
      } catch {
        continue
      }

      if (obj.error) throw new Error(String(obj.error))
      if (obj.run && handlers.onRun) handlers.onRun(obj.run)
      if (obj.plan && handlers.onPlan) handlers.onPlan(obj.plan)
      if (obj.status && handlers.onStatus) handlers.onStatus(obj.status)
      if (obj.operation && handlers.onOperation) handlers.onOperation(obj.operation)
      if (obj.usage && handlers.onUsage) handlers.onUsage(obj.usage)
      if (obj.delta) {
        fullText += String(obj.delta)
        if (handlers.onDelta) handlers.onDelta(String(obj.delta), fullText)
      }

      if (obj.done) {
        if (obj.reply && !fullText) fullText = String(obj.reply)
        if (handlers.onDone) handlers.onDone(obj)
        return {
          done: true,
          reply: fullText,
          latency_ms: Number(obj.latency_ms || 0),
          usage: obj.usage || null,
          reference: obj.reference || [],
          model: obj.model || '',
          run: obj.run || null,
          plan: obj.plan || [],
          operations: obj.operations || [],
        }
      }
    }
    return null
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const end = parseEventChunk(chunk)
      if (end?.done) return end
    }
  }

  if (buffer.trim()) {
    const end = parseEventChunk(buffer)
    if (end?.done) return end
  }

  if (handlers.onDone) handlers.onDone({ done: true, reply: fullText, latency_ms: 0 })
  return { done: true, reply: fullText, latency_ms: 0, usage: null, reference: [], model: '', run: null, plan: [], operations: [] }
}

export async function listMaterialsApi(baseUrl, courseId) {
  const base = getBackend(baseUrl)
  const url = courseId ? `${base}/courses/${courseId}/materials` : `${base}/materials`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export function uploadMaterialApi(baseUrl, formData, onProgress) {
  const url = `${getBackend(baseUrl)}/materials/upload`
  if (typeof onProgress !== 'function') {
    return fetch(url, { method: 'POST', body: formData }).then(async (res) => {
      const text = await res.text()
      if (!res.ok) {
        try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
        catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
      }
      return JSON.parse(text)
    })
  }
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText)) } catch (e) { resolve({}) }
      } else { reject(new Error(xhr.responseText || xhr.statusText)) }
    }
    xhr.onerror = () => reject(new Error('网络错误'))
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) {
        try { onProgress(Math.round((ev.loaded / ev.total) * 100)) } catch (e) {}
      }
    }
    xhr.send(formData)
  })
}

// ─── Course APIs ───

export async function listCoursesApi(baseUrl, ownerId = 'user1') {
  const url = `${getBackend(baseUrl)}/courses?owner_id=${encodeURIComponent(ownerId)}`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) { try { const j = JSON.parse(text); throw new Error(j.detail || text) } catch(e) { throw e } }
  return JSON.parse(text)
}

export async function createCourseApi(baseUrl, payload) {
  const url = `${getBackend(baseUrl)}/courses`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const text = await res.text()
  if (!res.ok) { try { const j = JSON.parse(text); throw new Error(j.detail || text) } catch(e) { throw e } }
  return JSON.parse(text)
}

export async function deleteCourseApi(baseUrl, courseId) {
  const url = `${getBackend(baseUrl)}/courses/${courseId}`
  const res = await fetch(url, { method: 'DELETE' })
  const text = await res.text()
  if (!res.ok) { try { const j = JSON.parse(text); throw new Error(j.detail || text) } catch(e) { throw e } }
  return JSON.parse(text)
}

export async function updateCourseApi(baseUrl, courseId, payload) {
  const url = `${getBackend(baseUrl)}/courses/${courseId}`
  const res = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const text = await res.text()
  if (!res.ok) { try { const j = JSON.parse(text); throw new Error(j.detail || text) } catch(e) { throw e } }
  return JSON.parse(text)
}

export async function listWorkspaceFilesApi(baseUrl, courseId) {
  const url = `${getBackend(baseUrl)}/courses/${courseId}/workspace/tree`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export async function readWorkspaceFileApi(baseUrl, courseId, path) {
  const params = new URLSearchParams({ path: String(path || '') })
  const url = `${getBackend(baseUrl)}/courses/${courseId}/workspace/file?${params.toString()}`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export async function saveWorkspaceFileApi(baseUrl, courseId, payload) {
  const url = `${getBackend(baseUrl)}/courses/${courseId}/workspace/file`
  const res = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export async function createWorkspaceFileApi(baseUrl, courseId, payload) {
  const url = `${getBackend(baseUrl)}/courses/${courseId}/workspace/file`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export async function createWorkspaceDirectoryApi(baseUrl, courseId, payload) {
  const url = `${getBackend(baseUrl)}/courses/${courseId}/workspace/directory`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export async function deleteWorkspaceFileApi(baseUrl, courseId, path) {
  const params = new URLSearchParams({ path: String(path || '') })
  const url = `${getBackend(baseUrl)}/courses/${courseId}/workspace/file?${params.toString()}`
  const res = await fetch(url, { method: 'DELETE' })
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export async function deleteWorkspaceDirectoryApi(baseUrl, courseId, path, recursive = false) {
  const params = new URLSearchParams({ path: String(path || ''), recursive: String(recursive) })
  const url = `${getBackend(baseUrl)}/courses/${courseId}/workspace/directory?${params.toString()}`
  const res = await fetch(url, { method: 'DELETE' })
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export async function renameWorkspaceItemApi(baseUrl, courseId, payload) {
  const url = `${getBackend(baseUrl)}/courses/${courseId}/workspace/rename`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}

export function getMaterialViewUrl(baseUrl, documentId) {
  return `${getBackend(baseUrl)}/materials/${documentId}/view`
}

export async function searchMaterialsApi(baseUrl, payload) {
  const url = `${getBackend(baseUrl)}/materials/search`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const text = await res.text()
  if (!res.ok) {
    try { const j = JSON.parse(text); throw new Error(j.detail || JSON.stringify(j)) }
    catch (e) { if (e.message !== text) throw e; throw new Error(text || res.statusText) }
  }
  return JSON.parse(text)
}
