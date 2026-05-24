export const ATTACH_CONTEXT_MAX_FILES = 12
export const ATTACH_CONTEXT_MAX_CHARS = 60000
export const ATTACH_CONTEXT_FILE_CHARS = 12000
export const SELECTED_TEXT_CONTEXT_MAX_CHARS = 40000
export const PASTED_TEXT_CONTEXT_MAX_CHARS = 60000
export const PASTED_TEXT_LINE_THRESHOLD = 4
export const PASTED_TEXT_CHAR_THRESHOLD = 900

export function buildThreadTitle(messages) {
  const firstUser = (messages || []).find(x => x?.role === 'user' && String(x?.content || '').trim())
  if (!firstUser) return ''
  return String(firstUser.content || '').trim().replace(/\s+/g, ' ').slice(0, 18)
}
