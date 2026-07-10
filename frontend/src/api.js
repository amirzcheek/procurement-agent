// Доступ к бэкенду. На портале — под слагом (VITE_API_BASE=/agents/procurement),
// локально — через vite-прокси /api → :8090.
export const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export async function fetchConfig() {
  const r = await fetch(`${API_BASE}/config`)
  if (!r.ok) throw new Error('config недоступен')
  return r.json()
}

export function exportUrl(jobId, period) {
  const p = new URLSearchParams()
  if (period?.months != null) p.set('period_months', String(period.months))
  if (period?.dateFrom) p.set('date_from', period.dateFrom)
  if (period?.dateTo) p.set('date_to', period.dateTo)
  const qs = p.toString()
  return `${API_BASE}/export/${jobId}${qs ? '?' + qs : ''}`
}

// Исторический ценовой анализ по job за выбранный период (пересчёт при смене периода).
export async function historicalAnalysis(jobId, period) {
  const r = await fetch(`${API_BASE}/analysis/historical`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      job_id: jobId,
      period_months: period?.months ?? null,
      date_from: period?.dateFrom ?? null,
      date_to: period?.dateTo ?? null,
    }),
  })
  if (!r.ok) throw new Error(`historical ${r.status}`)
  return r.json()
}

// База знаний: извлечь позиции из договора/КП для подтверждения.
export async function knowledgeExtract(file) {
  const form = new FormData()
  form.append('file', file)
  const r = await fetch(`${API_BASE}/knowledge/extract`, { method: 'POST', body: form })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.error || `extract ${r.status}`)
  return data
}

// База знаний: сохранить подтверждённый договор/КП.
export async function knowledgeConfirm(header, items) {
  const r = await fetch(`${API_BASE}/knowledge/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ header, items }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.error || `confirm ${r.status}`)
  return data
}

// Договоры (Этап 2).
export async function listContracts() {
  const r = await fetch(`${API_BASE}/contracts`)
  if (!r.ok) throw new Error(`contracts ${r.status}`)
  return r.json()
}

export async function getContract(id) {
  const r = await fetch(`${API_BASE}/contracts/${id}`)
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.error || `contract ${r.status}`)
  return data
}

export async function runContractCheck(id, periodMonths) {
  const r = await fetch(`${API_BASE}/contracts/${id}/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ period_months: periodMonths ?? null }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.error || `check ${r.status}`)
  return data
}

export async function getConclusion(id, period) {
  const p = new URLSearchParams()
  if (period?.months != null) p.set('period_months', String(period.months))
  const r = await fetch(`${API_BASE}/contracts/${id}/conclusion?${p.toString()}`)
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.error || `conclusion ${r.status}`)
  return data
}

export async function confirmContract(id) {
  const r = await fetch(`${API_BASE}/contracts/${id}/confirm`, { method: 'POST' })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.error || `confirm ${r.status}`)
  return data
}

export function conclusionExportUrl(id, period) {
  const p = new URLSearchParams()
  if (period?.months != null) p.set('period_months', String(period.months))
  const qs = p.toString()
  return `${API_BASE}/contracts/${id}/export${qs ? '?' + qs : ''}`
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
