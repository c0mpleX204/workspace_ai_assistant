/**
 * Slash-command system for in-chat feature toggles.
 *
 * Commands:
 *   /thinking on|off   — toggle extended thinking
 *   /subagent on|off   — toggle parallel sub-agent retrieval
 *   /fc on|off         — toggle function calling for task planning
 *   /status            — show current runtime flags
 *   /help              — list all commands
 */

const STORAGE_KEY = 'runtime_flags_v1'

const FLAG_DEFAULTS = {
  thinking_enabled: true,
  subagent_enabled: true,
  fc_enabled: true,
}

const FLAG_LABELS = {
  thinking_enabled: '分步思考',
  subagent_enabled: '子代理并行',
  fc_enabled: 'Function Calling',
}

const FLAG_TOGGLE = {
  'thinking': 'thinking_enabled',
  'subagent': 'subagent_enabled',
  'fc': 'fc_enabled',
}

export function loadRuntimeFlags() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...FLAG_DEFAULTS }
    const data = JSON.parse(raw)
    return { ...FLAG_DEFAULTS, ...data }
  } catch {
    return { ...FLAG_DEFAULTS }
  }
}

export function saveRuntimeFlags(flags) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(flags))
  } catch { /* noop */ }
}

export function getRuntimeFlag(key) {
  const flags = loadRuntimeFlags()
  return flags[key] ?? FLAG_DEFAULTS[key]
}

export function setRuntimeFlag(key, value) {
  const flags = loadRuntimeFlags()
  flags[key] = value
  saveRuntimeFlags(flags)
  return flags
}

export function getRuntimeFlagLabels() {
  return FLAG_LABELS
}

/**
 * Try to match and execute a slash command.
 * Returns { handled: true, message: string, flags: object } if matched,
 * or { handled: false } if not a slash command.
 */
export function trySlashCommand(input) {
  const text = String(input || '').trim()
  if (!text.startsWith('/')) return { handled: false }

  const lower = text.toLowerCase()

  // /status
  if (lower === '/status' || lower === '/s') {
    const flags = loadRuntimeFlags()
    const parts = Object.entries(FLAG_LABELS).map(([key, label]) => {
      const on = flags[key] ?? false
      return `${label}: ${on ? 'ON' : 'OFF'}`
    })
    return {
      handled: true,
      message: '当前状态: ' + parts.join(' | '),
      flags,
    }
  }

  // /help
  if (lower === '/help' || lower === '/h' || lower === '/?') {
    return {
      handled: true,
      message: [
        '可用命令:',
        '  /thinking on|off  — 分步思考',
        '  /subagent on|off  — 子代理并行',
        '  /fc on|off        — Function Calling',
        '  /status           — 查看当前状态',
        '  /help             — 显示此帮助',
      ].join('\n'),
      flags: loadRuntimeFlags(),
    }
  }

  // /thinking on|off, /subagent on|off, /fc on|off
  for (const [cmd, flagKey] of Object.entries(FLAG_TOGGLE)) {
    const onMatch = lower.match(new RegExp(`^/${cmd}\\s+on$`))
    const offMatch = lower.match(new RegExp(`^/${cmd}\\s+off$`))
    if (onMatch) {
      const flags = setRuntimeFlag(flagKey, true)
      return { handled: true, message: `${FLAG_LABELS[flagKey]}: 已开启`, flags }
    }
    if (offMatch) {
      const flags = setRuntimeFlag(flagKey, false)
      return { handled: true, message: `${FLAG_LABELS[flagKey]}: 已关闭`, flags }
    }
  }

  // Unknown command starting with /
  if (text.startsWith('/')) {
    return {
      handled: true,
      message: `未知命令: ${text.split(' ')[0]}\n输入 /help 查看可用命令`,
      flags: loadRuntimeFlags(),
    }
  }

  return { handled: false }
}
