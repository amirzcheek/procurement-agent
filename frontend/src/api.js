// Доступ к бэкенду. На портале — под слагом (VITE_API_BASE=/agents/procurement),
// локально — через vite-прокси /api → :8090.
export const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export async function fetchConfig() {
  const r = await fetch(`${API_BASE}/config`)
  if (!r.ok) throw new Error('config недоступен')
  return r.json()
}

export function exportUrl(jobId) {
  return `${API_BASE}/export/${jobId}`
}

/**
 * POST /analyze c multipart-файлом. Ответ — SSE-поток.
 * Парсим поток вручную (EventSource не умеет POST) и зовём onEvent(obj) на каждое событие.
 */
export async function analyze(file, onEvent, signal) {
  const form = new FormData()
  form.append('file', file)

  const resp = await fetch(`${API_BASE}/analyze`, { method: 'POST', body: form, signal })
  if (!resp.ok || !resp.body) {
    const txt = await resp.text().catch(() => '')
    throw new Error(`Ошибка сервера ${resp.status}: ${txt}`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE: события разделены пустой строкой. sse_starlette использует CRLF (\r\n\r\n),
    // спека также допускает LF (\n\n) — поддерживаем оба.
    let m
    while ((m = /\r\n\r\n|\n\n/.exec(buffer))) {
      const chunk = buffer.slice(0, m.index)
      buffer = buffer.slice(m.index + m[0].length)
      const dataLine = chunk
        .split(/\r?\n/)
        .find((l) => l.startsWith('data:'))
      if (!dataLine) continue
      const json = dataLine.slice(5).trim()
      if (!json) continue
      try {
        onEvent(JSON.parse(json))
      } catch {
        // битый кусок — пропускаем
      }
    }
  }
}
