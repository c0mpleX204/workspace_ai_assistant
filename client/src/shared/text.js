export function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = e => resolve(e.target.result)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

export function fileNameFromPath(path) {
  const parts = String(path || '').split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] || path || 'untitled'
}

export function formatTokenUsage(usage) {
  if (!usage) return ''
  if (usage.pending) {
    const est = Number(usage.output_tokens_estimate || 0)
    return `tokens 统计中 · cache -- · out ${est ? `~${est}` : '--'}`
  }
  const hit = Number(usage.cache_hit_tokens || 0)
  const out = Number(usage.output_tokens || 0)
  const input = Number(usage.input_tokens || 0)
  const total = Number(usage.total_tokens || 0)
  const parts = []
  if (hit) parts.push(`cache ${hit}`)
  if (input) parts.push(`in ${input}`)
  if (out) parts.push(`out ${out}`)
  if (total) parts.push(`total ${total}`)
  return parts.join(' · ')
}

export function estimateOutputTokens(text) {
  const value = String(text || '')
  if (!value.trim()) return 0
  const cjkCount = (value.match(/[\u3400-\u9fff]/g) || []).length
  const latinText = value.replace(/[\u3400-\u9fff]/g, '')
  return Math.max(1, Math.round(cjkCount * 1.25 + latinText.length / 4))
}

export function formatMessageTime(value) {
  if (!value) return ''
  const date = value ? new Date(value) : new Date()
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export function displayMessageContent(content) {
  const text = String(content || '')
  if (/^(None)+$/.test(text.trim()) && text.length > 16) {
    return '上一轮流式空片段已过滤，请重试这条请求。'
  }
  return text
}

export function citationLabel(ref) {
  const target = ref?.target || {}
  const kind = ref?.type || target.kind || 'source'
  const title = ref?.doucument_title || fileNameFromPath(ref?.source_path || target.path || '')
  if (target.line_start || ref?.line_start) {
    const start = target.line_start || ref.line_start
    const end = target.line_end || ref.line_end || start
    return `${title} L${start}${end !== start ? `-${end}` : ''}`
  }
  if (target.page_no || ref?.page_no) {
    const page = target.page_no || ref.page_no
    return `${title} ${kind === 'slide' ? 'slide' : 'p'}${page}`
  }
  return title || ref?.ref_id || 'source'
}
