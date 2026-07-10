import React, { useEffect, useRef, useState } from 'react'
import { analyze, exportUrl, fetchConfig, historicalAnalysis } from './api.js'
import { useI18n } from './i18n.jsx'
import { useSession } from './auth/useSession.js'
import Navbar from './components/Navbar.jsx'
import Summary from './components/Summary.jsx'
import ItemsTable from './components/ItemsTable.jsx'
import PeriodSelector from './components/PeriodSelector.jsx'
import HistoricalPanel from './components/HistoricalPanel.jsx'
import KnowledgeView from './components/KnowledgeView.jsx'
import ContractsView from './components/ContractsView.jsx'
import AnalyticsView from './components/AnalyticsView.jsx'
import SearchView from './components/SearchView.jsx'
import EmployeesView from './components/EmployeesView.jsx'
import AuditView from './components/AuditView.jsx'

// Вкладки и роли, которым они доступны (Этап 2 ч.3).
const TABS = [
  { key: 'analyze', label: 'tab_analyze', roles: ['procurer', 'manager', 'admin'] },
  { key: 'knowledge', label: 'tab_knowledge', roles: ['procurer', 'admin'] },
  { key: 'contracts', label: 'tab_contracts', roles: ['procurer', 'manager', 'admin'] },
  { key: 'analytics', label: 'tab_analytics', roles: ['manager', 'admin'] },
  { key: 'search', label: 'tab_search', roles: ['manager', 'admin'] },
  { key: 'employees', label: 'tab_employees', roles: ['procurer', 'manager', 'admin'] },
  { key: 'audit', label: 'tab_audit', roles: ['admin'] },
]

export default function App() {
  const { t } = useI18n()
  const { user } = useSession()
  const [tab, setTab] = useState('analyze')
  const [config, setConfig] = useState(null)
  const [openContractId, setOpenContractId] = useState(null)

  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('idle') // idle | running | done | error
  const [progress, setProgress] = useState({ current: 0, total: 0, label: '' })
  const [items, setItems] = useState([])
  const [summary, setSummary] = useState(null)
  const [jobId, setJobId] = useState(null)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  const [period, setPeriod] = useState({ months: 6 })
  const [historical, setHistorical] = useState(null)
  const [histLoading, setHistLoading] = useState(false)

  useEffect(() => {
    fetchConfig()
      .then((c) => {
        setConfig(c)
        if (c?.default_price_period_months != null) setPeriod({ months: c.default_price_period_months })
      })
      .catch(() => setConfig(null))
  }, [])

  const dbEnabled = !!config?.db_enabled

  // Пересчёт исторического анализа при готовом job и смене периода.
  useEffect(() => {
    if (status !== 'done' || !jobId || !dbEnabled) return
    // custom-период без обеих дат не считаем
    if (period.months == null && !period.dateFrom && !period.dateTo) return
    let active = true
    setHistLoading(true)
    historicalAnalysis(jobId, period)
      .then((h) => active && setHistorical(h))
      .catch(() => active && setHistorical(null))
      .finally(() => active && setHistLoading(false))
    return () => {
      active = false
    }
  }, [status, jobId, dbEnabled, period])

  async function onAnalyze() {
    if (!file) return
    setStatus('running')
    setItems([])
    setSummary(null)
    setJobId(null)
    setError(null)
    setHistorical(null)
    const scanLikely = file.type.startsWith('image/') || file.name.toLowerCase().endsWith('.pdf')
    setProgress({ current: 0, total: 0, label: scanLikely ? t('ocr_recognizing') : t('progress_parse') })
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await analyze(
        file,
        (ev) => {
          switch (ev.type) {
            case 'job': setJobId(ev.job_id); break
            case 'extract': setProgress((p) => ({ ...p, label: t('progress_extract') })); break
            case 'parsed': setProgress({ current: 0, total: ev.count, label: `${t('found_items')}: ${ev.count}` }); break
            case 'item_start':
              setProgress({ current: ev.index, total: ev.total, label: `${t('position')} ${ev.index + 1}/${ev.total}: ${ev.name}` })
              break
            case 'item_done':
              setItems((prev) => [...prev, ev.report])
              setProgress((p) => ({ ...p, current: ev.index + 1 }))
              break
            case 'done': setSummary(ev.report.summary); setItems(ev.report.items); setStatus('done'); break
            case 'error': setError(ev.message); setStatus('error'); break
            default: break
          }
        },
        controller.signal
      )
      setStatus((s) => (s === 'error' ? s : 'done'))
    } catch (e) {
      if (e.name !== 'AbortError') { setError(String(e.message || e)); setStatus('error') }
    }
  }

  const running = status === 'running'
  const pct = progress.total ? Math.round((progress.current / progress.total) * 100) : 0

  return (
    <div className="page">
      <div className="wrap">
        <Navbar />

        <nav className="tabs">
          {TABS.filter((tb) => tb.roles.includes(user.role || 'procurer')).map((tb) => (
            <button key={tb.key} className={'tab' + (tab === tb.key ? ' active' : '')} onClick={() => setTab(tb.key)}>
              {t(tb.key === 'employees' && (user.role || 'procurer') === 'procurer' ? 'tab_my_stats' : tb.label)}
            </button>
          ))}
        </nav>

        <div className="disclaimer" role="note">⚠️ {t('disclaimer')}</div>

        {tab === 'knowledge' ? (
          <KnowledgeView dbEnabled={dbEnabled} />
        ) : tab === 'contracts' ? (
          <ContractsView dbEnabled={dbEnabled} openId={openContractId} />
        ) : tab === 'analytics' ? (
          <AnalyticsView dbEnabled={dbEnabled} />
        ) : tab === 'search' ? (
          <SearchView dbEnabled={dbEnabled} onOpenContract={(id) => { setOpenContractId(id); setTab('contracts') }} />
        ) : tab === 'employees' ? (
          <EmployeesView dbEnabled={dbEnabled} selfOnly={user.role === 'procurer'} />
        ) : tab === 'audit' ? (
          <AuditView dbEnabled={dbEnabled} />
        ) : (
          <>
            <h2 className="page-title">{t('agent_name')}</h2>
            <p className="page-subtitle">{t('subtitle')}</p>

            <section className="card controls">
              <label className="file-input">
                <input type="file" accept=".xlsx,.xlsm,.pdf,.png,.jpg,.jpeg,.tiff,.webp" onChange={(e) => { setFile(e.target.files?.[0] || null); setError(null) }} disabled={running} />
                <span>{file ? file.name : t('pick_file')}</span>
              </label>
              <div className="controls-actions">
                {!running ? (
                  <button className="btn btn-primary" onClick={onAnalyze} disabled={!file}>{t('analyze_btn')}</button>
                ) : (
                  <button className="btn btn-stop" onClick={() => { abortRef.current?.abort(); setStatus('idle') }}>{t('cancel_btn')}</button>
                )}
                {jobId && status === 'done' && (
                  <a className="btn btn-ghost" href={exportUrl(jobId, period)}>{t('download_xlsx')}</a>
                )}
              </div>
              {config && (
                <div className="config-badges">
                  <span className="badge">{config.search_provider}</span>
                  {config.db_enabled && <span className="badge">БЗ ✓</span>}
                </div>
              )}
            </section>

            {running && (
              <section className="progress">
                <div className="progress-bar"><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
                <div className="progress-label">{progress.label}</div>
              </section>
            )}

            {error && <div className="error">{t('err_prefix')}: {error}</div>}
            {summary && <Summary summary={summary} />}

            {items.length > 0 && (
              <>
                <h3 className="section-title">{t('market_title')}</h3>
                <ItemsTable items={items} />
              </>
            )}

            {status === 'done' && items.length > 0 && (
              <section className="hist-block">
                <PeriodSelector value={period} onChange={setPeriod} />
                {dbEnabled ? (
                  <HistoricalPanel historical={historical} loading={histLoading} />
                ) : (
                  <div className="notice">{t('hist_disabled')}</div>
                )}
              </section>
            )}

            {status === 'idle' && !items.length && <p className="muted hint">{t('hint_idle')}</p>}
          </>
        )}
      </div>
    </div>
  )
}
