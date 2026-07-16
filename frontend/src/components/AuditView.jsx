import React, { useEffect, useState } from 'react'
import { getAudit } from '../api.js'
import { useI18n } from '../i18n.jsx'

const ACTIONS = ['', 'save_contract', 'run_checks', 'confirm_contract']
const RISK_CLASS = { low: 'green', medium: 'yellow', high: 'red', unknown: 'gray' }

function RiskTag({ level }) {
  const { t } = useI18n()
  if (!level) return null
  return <span className={`flag ${RISK_CLASS[level] || 'gray'}`}>{t('risk_' + level)}</span>
}

// Человекочитаемые детали вместо сырого JSON.
function Details({ action, details }) {
  const { t } = useI18n()
  if (!details || typeof details !== 'object') return null

  if (action === 'run_checks') {
    const risks = details.risks || {}
    return (
      <span className="audit-details">
        <b>{t('contract_risk')}:</b> <RiskTag level={details.risk_level} />
        {Object.entries(risks).map(([k, v]) => (
          <span key={k} className="audit-chip">{t('chk_' + k)} <RiskTag level={v} /></span>
        ))}
      </span>
    )
  }
  if (action === 'save_contract') {
    return (
      <span className="audit-details">
        {details.items != null && <span className="audit-chip">{details.items} {t('kb_items')}</span>}
        {details.number && <span className="audit-chip">№ {details.number}</span>}
        {details.source_type && <span className="audit-chip">{details.source_type}</span>}
      </span>
    )
  }
  if (action === 'confirm_contract') {
    return <span className="audit-details"><b>{t('contract_risk')}:</b> <RiskTag level={details.risk_level} /></span>
  }
  return (
    <span className="muted">
      {Object.entries(details).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(', ')}
    </span>
  )
}

export default function AuditView({ dbEnabled }) {
  const { t } = useI18n()
  const [f, setF] = useState({ user: '', action: '', date_from: '', date_to: '' })
  const [rows, setRows] = useState([])
  const [error, setError] = useState(null)

  async function load() {
    try {
      const d = await getAudit(f)
      setRows(d.records || [])
    } catch (e) {
      setError(String(e.message || e))
    }
  }
  useEffect(() => { if (dbEnabled) load() }, [dbEnabled])

  if (!dbEnabled) return <div className="notice">{t('hist_disabled')}</div>
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  return (
    <div>
      <h2 className="page-title">{t('tab_audit')}</h2>
      <section className="card">
        <div className="search-grid">
          <label className="field"><span className="field__label">{t('a_user')}</span><input value={f.user} onChange={set('user')} /></label>
          <label className="field"><span className="field__label">{t('a_action')}</span>
            <select value={f.action} onChange={set('action')}>
              {ACTIONS.map((a) => <option key={a} value={a}>{a || t('s_any')}</option>)}
            </select>
          </label>
          <label className="field"><span className="field__label">{t('date_from')}</span><input type="date" value={f.date_from} onChange={set('date_from')} /></label>
          <label className="field"><span className="field__label">{t('date_to')}</span><input type="date" value={f.date_to} onChange={set('date_to')} /></label>
        </div>
        <div className="controls-actions" style={{ marginTop: 14 }}>
          <button className="btn btn-primary" onClick={load}>{t('search_run')}</button>
        </div>
      </section>
      {error && <div className="error">{t('err_prefix')}: {error}</div>}
      <div className="table-wrap" style={{ marginTop: 16 }}>
        <table className="items">
          <thead><tr><th>{t('a_when')}</th><th>{t('a_user')}</th><th>{t('a_action')}</th><th>{t('a_entity')}</th><th>{t('a_details')}</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{(r.created_at || '').replace('T', ' ').slice(0, 19)}</td>
                <td className="name">{r.user_email || '—'}</td>
                <td>{r.action}</td>
                <td>{r.entity_type} {r.entity_id ? `#${r.entity_id}` : ''}</td>
                <td className="reco"><Details action={r.action} details={r.details} /></td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={5} className="muted">—</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
