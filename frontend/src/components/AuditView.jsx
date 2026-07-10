import React, { useEffect, useState } from 'react'
import { getAudit } from '../api.js'
import { useI18n } from '../i18n.jsx'

const ACTIONS = ['', 'save_contract', 'run_checks', 'confirm_contract']

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
                <td className="reco">{r.details ? JSON.stringify(r.details) : ''}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={5} className="muted">—</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
