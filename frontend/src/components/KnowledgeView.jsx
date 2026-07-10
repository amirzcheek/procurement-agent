import React, { useState } from 'react'
import { knowledgeExtract, knowledgeConfirm } from '../api.js'
import { useI18n } from '../i18n.jsx'

// База знаний: загрузить договор/КП → извлечь позиции → подтвердить реквизиты → сохранить.
export default function KnowledgeView({ dbEnabled }) {
  const { t, locale } = useI18n()
  const [file, setFile] = useState(null)
  const [items, setItems] = useState([])
  const [header, setHeader] = useState({ number: '', date: '', supplier: '', customer: '', funding_source: '' })
  const [status, setStatus] = useState('idle') // idle | extracting | ready | saving | saved | error
  const [error, setError] = useState(null)

  async function onExtract() {
    if (!file) return
    setStatus('extracting')
    setError(null)
    setItems([])
    try {
      const res = await knowledgeExtract(file)
      setItems(res.items || [])
      setStatus('ready')
    } catch (e) {
      setError(String(e.message || e))
      setStatus('error')
    }
  }

  async function onSave() {
    setStatus('saving')
    setError(null)
    try {
      await knowledgeConfirm(header, items)
      setStatus('saved')
    } catch (e) {
      setError(String(e.message || e))
      setStatus('error')
    }
  }

  const fmt = (n) => (n == null ? '—' : new Intl.NumberFormat(locale).format(n))

  return (
    <div>
      <h2 className="page-title">{t('kb_title')}</h2>
      <p className="page-subtitle">{t('kb_desc')}</p>

      {!dbEnabled && <div className="notice">{t('hist_disabled')}</div>}

      <section className="card controls">
        <label className="file-input">
          <input
            type="file"
            accept=".xlsx,.xlsm,.pdf"
            disabled={status === 'extracting' || !dbEnabled}
            onChange={(e) => {
              setFile(e.target.files?.[0] || null)
              setItems([])
              setStatus('idle')
            }}
          />
          <span>{file ? file.name : t('kb_pick')}</span>
        </label>
        <button className="btn btn-primary" onClick={onExtract} disabled={!file || !dbEnabled || status === 'extracting'}>
          {status === 'extracting' ? t('kb_extracting') : t('kb_extract')}
        </button>
      </section>

      {error && <div className="error">{t('err_prefix')}: {error}</div>}
      {status === 'saved' && <div className="notice ok">{t('kb_saved')}</div>}

      {items.length > 0 && status !== 'saved' && (
        <>
          <p className="muted" style={{ margin: '16px 0 8px' }}>
            {t('kb_confirm_hint')} — {items.length} {t('kb_items')}
          </p>
          <section className="card">
            <div className="grid-2">
              <label className="field">
                <span className="field__label">{t('kb_number')}</span>
                <input value={header.number} onChange={(e) => setHeader({ ...header, number: e.target.value })} />
              </label>
              <label className="field">
                <span className="field__label">{t('kb_date')}</span>
                <input type="date" value={header.date} onChange={(e) => setHeader({ ...header, date: e.target.value })} />
              </label>
              <label className="field">
                <span className="field__label">{t('kb_supplier')}</span>
                <input value={header.supplier} onChange={(e) => setHeader({ ...header, supplier: e.target.value })} />
              </label>
              <label className="field">
                <span className="field__label">{t('kb_customer')}</span>
                <input value={header.customer} onChange={(e) => setHeader({ ...header, customer: e.target.value })} />
              </label>
              <label className="field">
                <span className="field__label">{t('kb_funding')}</span>
                <input value={header.funding_source} onChange={(e) => setHeader({ ...header, funding_source: e.target.value })} />
              </label>
            </div>
            <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={onSave} disabled={status === 'saving'}>
              {status === 'saving' ? t('kb_saving') : t('kb_save')}
            </button>
          </section>

          <div className="table-wrap" style={{ marginTop: 16 }}>
            <table className="items">
              <thead>
                <tr>
                  <th>{t('th_name')}</th>
                  <th>{t('th_qty')}</th>
                  <th>{t('col_unit')}</th>
                  <th>{t('col_unitprice')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => (
                  <tr key={i}>
                    <td className="name">{it.name}</td>
                    <td className="num">{fmt(it.qty)}</td>
                    <td>{it.unit || '—'}</td>
                    <td className="num">{fmt(it.unit_price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
