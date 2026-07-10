import React, { useState } from 'react'
import { searchContracts } from '../api.js'
import { useI18n } from '../i18n.jsx'

const RISK_CLASS = { low: 'green', medium: 'yellow', high: 'red', unknown: 'gray' }
const EMPTY = {
  number: '', supplier: '', product: '', model: '', manufacturer: '', category: '',
  date_from: '', date_to: '', price_min: '', price_max: '', risk_level: '', employee: '',
}

export default function SearchView({ dbEnabled, onOpenContract }) {
  const { t } = useI18n()
  const [f, setF] = useState(EMPTY)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)

  if (!dbEnabled) return <div className="notice">{t('hist_disabled')}</div>
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  async function run() {
    setError(null)
    try {
      const d = await searchContracts(f)
      setResults(d.results || [])
    } catch (e) {
      setError(String(e.message || e))
    }
  }

  return (
    <div>
      <h2 className="page-title">{t('tab_search')}</h2>
      <section className="card">
        <div className="search-grid">
          <label className="field"><span className="field__label">{t('s_number')}</span><input value={f.number} onChange={set('number')} /></label>
          <label className="field"><span className="field__label">{t('c_supplier')}</span><input value={f.supplier} onChange={set('supplier')} /></label>
          <label className="field"><span className="field__label">{t('s_product')}</span><input value={f.product} onChange={set('product')} /></label>
          <label className="field"><span className="field__label">{t('s_model')}</span><input value={f.model} onChange={set('model')} /></label>
          <label className="field"><span className="field__label">{t('s_manufacturer')}</span><input value={f.manufacturer} onChange={set('manufacturer')} /></label>
          <label className="field"><span className="field__label">{t('s_category')}</span><input value={f.category} onChange={set('category')} /></label>
          <label className="field"><span className="field__label">{t('date_from')}</span><input type="date" value={f.date_from} onChange={set('date_from')} /></label>
          <label className="field"><span className="field__label">{t('date_to')}</span><input type="date" value={f.date_to} onChange={set('date_to')} /></label>
          <label className="field"><span className="field__label">{t('s_price_min')}</span><input type="number" value={f.price_min} onChange={set('price_min')} /></label>
          <label className="field"><span className="field__label">{t('s_price_max')}</span><input type="number" value={f.price_max} onChange={set('price_max')} /></label>
          <label className="field"><span className="field__label">{t('s_risk')}</span>
            <select value={f.risk_level} onChange={set('risk_level')}>
              <option value="">{t('s_any')}</option>
              <option value="low">{t('risk_low')}</option>
              <option value="medium">{t('risk_medium')}</option>
              <option value="high">{t('risk_high')}</option>
            </select>
          </label>
          <label className="field"><span className="field__label">{t('s_employee')}</span><input value={f.employee} onChange={set('employee')} /></label>
        </div>
        <div className="controls-actions" style={{ marginTop: 14 }}>
          <button className="btn btn-primary" onClick={run}>{t('search_run')}</button>
        </div>
      </section>

      {error && <div className="error">{t('err_prefix')}: {error}</div>}

      {results && (
        <div className="table-wrap" style={{ marginTop: 16 }}>
          <table className="items">
            <thead><tr><th>{t('c_number')}</th><th>{t('c_date')}</th><th>{t('c_supplier')}</th><th>{t('contract_risk')}</th><th>{t('c_status')}</th></tr></thead>
            <tbody>
              {results.map((c) => (
                <tr key={c.id} className="clickable" onClick={() => onOpenContract(c.id)}>
                  <td className="name">{c.number || `#${c.id}`}</td>
                  <td>{c.date || '—'}</td>
                  <td>{c.supplier || '—'}</td>
                  <td>{c.risk_level ? <span className={`flag ${RISK_CLASS[c.risk_level]}`}>{t('risk_' + c.risk_level)}</span> : '—'}</td>
                  <td>{t('status_' + c.status)}</td>
                </tr>
              ))}
              {results.length === 0 && <tr><td colSpan={5} className="muted">—</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
