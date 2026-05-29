export const THREAD_KEY_PREFIX = 'desktop_chat_threads_v1:'
export const PROJECT_THREAD_KEY_PREFIX = 'project_chat_threads_v1:'
export const THREAD_DEFAULT_TITLE = '新对话'

export function buildChatThreadTitle(messages) {
  const firstUser = (messages || []).find(x => x?.role === 'user' && String(x?.content || '').trim())
  if (!firstUser) return THREAD_DEFAULT_TITLE
  const text = String(firstUser.content || '').trim().replace(/\s+/g, ' ')
  return text.slice(0, 18) || THREAD_DEFAULT_TITLE
}

export function normalizeThreadTitle(value, fallback = THREAD_DEFAULT_TITLE) {
  const text = String(value || '').trim()
  if (!text || text === 'New chat') return fallback
  return text
}

export function createChatThread(id = '') {
  const now = Date.now()
  return {
    id: id || `chat_${now}_${Math.random().toString(36).slice(2, 8)}`,
    title: THREAD_DEFAULT_TITLE,
    messages: [],
    createdAt: now,
    updatedAt: now,
  }
}

export function createProjectChatThread(courseId, id = '') {
  const now = Date.now()
  return {
    id: id || `course_${courseId}_${now}_${Math.random().toString(36).slice(2, 8)}`,
    title: THREAD_DEFAULT_TITLE,
    createdAt: now,
    updatedAt: now,
  }
}

export function normalizeChatThreads(raw) {
  if (!Array.isArray(raw)) return []
  return raw
    .filter(x => x && typeof x.id === 'string' && x.id.trim())
    .map(x => {
      const msgs = Array.isArray(x.messages) ? x.messages : []
      return {
        id: String(x.id),
        title: normalizeThreadTitle(x.title, buildChatThreadTitle(msgs)),
        type: x.type || undefined,
        personaId: x.personaId || undefined,
        messages: msgs,
        createdAt: Number(x.createdAt || Date.now()),
        updatedAt: Number(x.updatedAt || Date.now()),
      }
    })
}

export function normalizeProjectThreads(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const result = {}
  for (const [courseId, items] of Object.entries(raw)) {
    if (!Array.isArray(items)) continue
    const cleaned = items
      .filter(x => x && typeof x.id === 'string' && x.id.trim())
      .map(x => ({
        id: String(x.id),
        title: normalizeThreadTitle(x.title),
        type: x.type || undefined,
        pdfDocumentId: x.pdfDocumentId || undefined,
        pdfUrl: x.pdfUrl || undefined,
        pdfInitialPage: x.pdfInitialPage || undefined,
        createdAt: Number(x.createdAt || Date.now()),
        updatedAt: Number(x.updatedAt || Date.now()),
      }))
    if (cleaned.length > 0) result[String(courseId)] = cleaned
  }
  return result
}
