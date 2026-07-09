import React, { useEffect, useRef, useState } from 'react'
import { analyze, exportUrl, fetchConfig } from './api.js'
import Navbar from './components/Navbar.jsx'
import Summary from './components/Summary.jsx'
import ItemsTable from './components/ItemsTable.jsx'

const DISCLAIMER =
  'Предварительный анализ. Цены найдены автоматически и требуют проверки человеком. ' +
  'Это подсказка, а не окончательное заключение.'

export default function App() {
  const [file, setFile] = useState(null)
  const [config, setConfig] = useState(null)
  const [status, setStatus] = useState('idle') // idle | running | done | error
  const [progress, setProgress] = useState({ current: 0, total: 0, label: '' })
  const [items, setItems] = useState([])
  const [summary, setSummary] = useState(null)
  const [jobId, setJobId] = useState(null)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  useEffect(() => {
    fetchConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  function onPick(e) {
    setFile(e.target.files?.[0] || null)
    setError(null)
  }

  async function onAnalyze() {
    if (!file) return
    setStatus('running')
    setItems([])
    setSummary(null)
    setJobId(null)
    setError(null)
    setProgress({ current: 0, total: 0, label: 'Извлечение и разбор позиций…' })

    const controller = new AbortController()
    abortRef.current = controller

    try {
      await analyze(
        file,
        (ev) => {
          switch (ev.type) {
            case 'job':
              setJobId(ev.job_id)
              break
            case 'extract':
              setProgress((p) => ({ ...p, label: 'Распознаём позиции из таблицы…' }))
              break
            case 'parsed':
              setProgress({ current: 0, total: ev.count, label: `Найдено позиций: ${ev.count}` })
              break
            case 'item_start':
              setProgress({
                current: ev.index,
                total: ev.total,
                label: `Позиция ${ev.index + 1}/${ev.total}: ${ev.name}`,
              })
              break
            case 'item_done':
              setItems((prev) => [...prev, ev.report])
              setProgress((p) => ({ ...p, current: ev.index + 1 }))
              break
            case 'done':
              setSummary(ev.report.summary)
              setItems(ev.report.items)
              setStatus('done')
              break
            case 'error':
              setError(ev.message)
              setStatus('error')
              break
            default:
              break
          }
        },
        controller.signal
      )
      setStatus((s) => (s === 'error' ? s : 'done'))
    } catch (e) {
      if (e.name !== 'AbortError') {
        setError(String(e.message || e))
        setStatus('error')
      }
    }
  }

  function onCancel() {
    abortRef.current?.abort()
    setStatus('idle')
  }

  const running = status === 'running'
  const pct = progress.total ? Math.round((progress.current / progress.total) * 100) : 0

  return (
    <div className="page">
      <div className="wrap">
        <Navbar />

        <h1 className="page-title">Анализатор закупок</h1>
        <p className="page-subtitle">
          Проверка цен коммерческого предложения по казахстанским площадкам. Загрузите КП —
          система извлечёт позиции, найдёт рыночные цены и пометит подозрения на завышение.
        </p>

        <div className="disclaimer" role="note">
          ⚠️ {DISCLAIMER}
        </div>

        <section className="card controls">
          <label className="file-input">
            <input type="file" accept=".xlsx,.xlsm,.pdf" onChange={onPick} disabled={running} />
            <span>{file ? file.name : 'Выберите файл КП (.xlsx или текстовый .pdf)'}</span>
          </label>
          <div className="controls-actions">
            {!running ? (
              <button className="btn btn-primary" onClick={onAnalyze} disabled={!file}>
                Анализировать
              </button>
            ) : (
              <button className="btn btn-stop" onClick={onCancel}>
                Остановить
              </button>
            )}
            {jobId && status === 'done' && (
              <a className="btn btn-ghost" href={exportUrl(jobId)}>
                ⬇ Скачать xlsx
              </a>
            )}
          </div>
          {config && (
            <div className="config-badges">
              <span className="badge">поиск: {config.search_provider}</span>
              <span className="badge">модель: {config.llm_model}</span>
            </div>
          )}
        </section>

        {running && (
          <section className="progress">
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${pct}%` }} />
            </div>
            <div className="progress-label">{progress.label}</div>
          </section>
        )}

        {error && <div className="error">Ошибка: {error}</div>}

        {summary && <Summary summary={summary} />}

        {items.length > 0 && <ItemsTable items={items} />}

        {status === 'idle' && !items.length && (
          <p className="muted hint">
            Позиции обрабатываются последовательно — при реальном поиске это может занять время
            (локальный LLM на CPU + загрузка страниц магазинов).
          </p>
        )}
      </div>
    </div>
  )
}
