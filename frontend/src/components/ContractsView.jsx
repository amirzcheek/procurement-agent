import React, { useEffect, useState } from 'react'
import {
  listContracts, getContract, runContractCheck,
  getConclusion, confirmContract, conclusionExportUrl,
} from '../api.js'
import { useI18n } from '../i18n.jsx'
import { useSession } from '../auth/useSession.js'
import PeriodSelector from './PeriodSelector.jsx'
import HistoricalPanel from './HistoricalPanel.jsx'

const RISK_CLASS = { low: 'green', medium: 'yellow', high: 'red', unknown: 'gray' }
const CHECK_TITLE = {
  characteristics: 'chk_characteristics', price: 'chk_price',
  quantity: 'chk_quantity', conditions: 'chk_conditions',
}

function RiskBadge({ level }) {
  const { t } = useI18n()
  return <span className={`flag ${RISK_CLASS[level] || 'gray'}`}>{t('risk_' + (level || 'unknown'))}</span>
}

function CheckBlock({ check }) {
  const { t, locale } = useI18n()
  const r = check.result || {}
  const f = check.findings || {}
  const fmt = (n) => (n == null ? '—' : new Intl.NumberFormat(locale).format(n))
  return (
    <div className={`card check-block row-${RISK_CLASS[check.risk_level] || 'gray'}`}>
      <div className="check-head">
        <strong>{t(CHECK_TITLE[check.type] || check.type)}</strong>
        <RiskBadge level={check.risk_level} />
      </div>
      {check.type === 'characteristics' && (
        <div className="check-body">
          {r.compared === 0 ? <div className="muted">{t('chk_no_data')}</div> : (
            <>
              <div className="muted">{t('chk_compared')}: {r.compared}, {t('chk_with_diff')}: {r.with_differences}</div>
              {(f.items || []).map((it, i) => (
                <div key={i} className="finding"><b>{it.item}</b> · {(it.differences || []).join('; ') || it.reason}</div>
              ))}
            </>
          )}
        </div>
      )}
      {check.type === 'price' && (
        <div className="check-body">
          <div className="muted">{r.period_label}</div>
          <div className="table-wrap">
            <table className="items">
              <thead><tr><th>{t('th_name')}</th><th>{t('th_kp_price')}</th><th>{t('hist_range')}</th><th>{t('hist_risk')}</th></tr></thead>
              <tbody>
                {(r.items || []).map((it, i) => (
                  <tr key={i} className={`row-${RISK_CLASS[it.risk_level] || 'gray'}`}>
                    <td className="name">{it.item}</td>
                    <td className="num">{fmt(it.kp_unit_price)}</td>
                    <td className="num">{fmt(it.combined_min)} – {fmt(it.combined_max)} <small className="muted">({it.combined_count})</small></td>
                    <td><RiskBadge level={it.risk_level} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {check.type === 'quantity' && (
        <div className="check-body">
          {r.note ? <div className="muted">{t('chk_one_source')}</div>
            : (f.mismatches || []).length === 0 ? <div className="muted">✓</div>
            : (f.mismatches || []).map((m, i) => (
              <div key={i} className="finding"><b>{m.item}</b>: {Object.entries(m.per_source).map(([s, q]) => `${s}=${q}`).join(', ')}</div>
            ))}
        </div>
      )}
      {check.type === 'conditions' && (
        <div className="check-body">
          {(r.present || []).length > 0 && <div className="muted">{t('chk_present')}: {(r.present || []).join(', ')}</div>}
          {(f.missing_critical || []).length > 0 && <div className="finding err">{t('chk_missing')}: {f.missing_critical.join(', ')}</div>}
          {(f.missing_extra || []).length > 0 && <div className="finding">{t('chk_missing')}: {f.missing_extra.join(', ')}</div>}
        </div>
      )}
    </div>
  )
}

function ContractDetail({ id, onBack }) {
  const { t, locale } = useI18n()
  const { user } = useSession()
  const canWrite = ['procurer', 'admin'].includes(user.role)

  const [c, setC] = useState(null)
  const [error, setError] = useState(null)
  const [checking, setChecking] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [period, setPeriod] = useState({ months: 6 })
  const [conc, setConc] = useState(null)
  const [concLoading, setConcLoading] = useState(false)

  async function load() {
    try { setC(await getContract(id)) } catch (e) { setError(String(e.message || e)) }
  }
  useEffect(() => { load() }, [id])

  useEffect(() => {
    let active = true
    setConcLoading(true)
    getConclusion(id, period)
      .then((d) => active && setConc(d))
      .catch(() => active && setConc(null))
      .finally(() => active && setConcLoading(false))
    return () => { active = false }
  }, [id, period])

  async function onCheck() {
    setChecking(true); setError(null)
    try { await runContractCheck(id, period.months); await load() }
    catch (e) { setError(String(e.message || e)) } finally { setChecking(false) }
  }
  async function onConfirm() {
    setConfirming(true); setError(null)
    try { await confirmContract(id); await load() }
    catch (e) { setError(String(e.message || e)) } finally { setConfirming(false) }
  }

  if (error) return <div><button className="back-link" onClick={onBack}>{t('contract_back')}</button><div className="error">{t('err_prefix')}: {error}</div></div>
  if (!c) return <p className="muted">…</p>
  const fmt = (n) => (n == null ? '—' : new Intl.NumberFormat(locale).format(n))

  return (
    <div>
      <button className="back-link" onClick={onBack}>{t('contract_back')}</button>
      <div className="conc-head">
        <h2 className="page-title" style={{ margin: 0 }}>
          {c.number || `#${c.id}`} <span className="muted" style={{ fontSize: 16 }}>{c.date || ''}</span>
        </h2>
        {c.risk_level && <span className="risk-pill"><span className="muted">{t('contract_risk')}:</span> <RiskBadge level={c.risk_level} /></span>}
        <span className="badge">{t('status_' + c.status)}</span>
      </div>
      <p className="page-subtitle">{c.supplier || ''} {c.customer ? `· ${c.customer}` : ''}</p>

      {!canWrite && <div className="notice">{t('manager_readonly')}</div>}

      <div className="controls-actions" style={{ margin: '10px 0 18px' }}>
        {canWrite && (
          <button className="btn btn-primary" onClick={onCheck} disabled={checking}>
            {checking ? t('checking') : t('run_check')}
          </button>
        )}
        {canWrite && c.status === 'draft' && (c.checks || []).length > 0 && (
          <button className="btn btn-ghost" onClick={onConfirm} disabled={confirming}>
            {confirming ? t('confirming') : t('confirm_contract')}
          </button>
        )}
        <a className="btn btn-ghost" href={conclusionExportUrl(id, period)}>{t('export_conclusion')}</a>
      </div>
      {c.status === 'checked' && <div className="notice ok">{t('confirmed_ok')}</div>}

      {(c.checks || []).length > 0 && (
        <>
          <h3 className="section-title">{t('checks_title')}</h3>
          <div className="checks-grid">{c.checks.map((ch, i) => <CheckBlock key={i} check={ch} />)}</div>
        </>
      )}

      {(c.risk_factors || []).length > 0 && (
        <>
          <h3 className="section-title">{t('risk_factors_title')}</h3>
          <ul className="factors">
            {c.risk_factors.map((f, i) => (
              <li key={i}><b>{f.factor}</b>{f.item ? ` — ${f.item}` : ''} <span className="muted">[{f.source}]</span></li>
            ))}
          </ul>
        </>
      )}

      {/* Заключение: период + рекомендации + история цен по обоим источникам */}
      <div className="hist-block">
        <h3 className="section-title">{t('conclusion_title')} <span className="muted">· {conc?.period_label || ''}</span></h3>
        <div className="disclaimer">⚠️ {t('disclaimer_short')}</div>
        <PeriodSelector value={period} onChange={setPeriod} />
        {conc?.recommendations?.length > 0 && (
          <>
            <h4 className="section-title" style={{ fontSize: 14 }}>{t('recommendations_title')}</h4>
            <ul className="recs">{conc.recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul>
          </>
        )}
        <HistoricalPanel historical={conc ? { enabled: true, period_label: conc.period_label, items: conc.items } : null} loading={concLoading} />
      </div>

      <h3 className="section-title">{t('contract_items')} ({(c.items || []).length})</h3>
      <div className="table-wrap">
        <table className="items">
          <thead><tr><th>{t('th_name')}</th><th>Model</th><th>{t('c_supplier')}</th><th>{t('th_qty')}</th><th>{t('col_unitprice')}</th></tr></thead>
          <tbody>
            {(c.items || []).map((it) => (
              <tr key={it.id}>
                <td className="name">{it.name}</td>
                <td>{it.model || '—'}</td>
                <td>{it.manufacturer || '—'}</td>
                <td className="num">{fmt(it.qty)} {it.unit || ''}</td>
                <td className="num">{fmt(it.unit_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function ContractsView({ dbEnabled }) {
  const { t } = useI18n()
  const [data, setData] = useState(null)
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!dbEnabled) return
    listContracts().then(setData).catch((e) => setError(String(e.message || e)))
  }, [dbEnabled])

  if (!dbEnabled) return <div className="notice">{t('hist_disabled')}</div>
  if (selected) return <ContractDetail id={selected} onBack={() => setSelected(null)} />

  const rows = data?.contracts || []
  return (
    <div>
      <h2 className="page-title">{t('contracts_title')}</h2>
      {error && <div className="error">{t('err_prefix')}: {error}</div>}
      {rows.length === 0 ? (
        <p className="muted">{t('contracts_empty')}</p>
      ) : (
        <div className="table-wrap">
          <table className="items">
            <thead>
              <tr>
                <th>{t('c_number')}</th><th>{t('c_date')}</th><th>{t('c_supplier')}</th>
                <th>{t('c_items')}</th><th>{t('contract_risk')}</th><th>{t('c_status')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className="clickable" onClick={() => setSelected(c.id)}>
                  <td className="name">{c.number || `#${c.id}`}</td>
                  <td>{c.date || '—'}</td>
                  <td>{c.supplier || '—'}</td>
                  <td className="num">{c.items}</td>
                  <td>{c.risk_level ? <RiskBadge level={c.risk_level} /> : <span className="muted">—</span>}</td>
                  <td>{t('status_' + c.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
