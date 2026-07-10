import React, { useState } from 'react'
import { useI18n } from '../i18n.jsx'

function Delta({ v }) {
  if (v == null) return <span>—</span>
  const sign = v > 0 ? '+' : ''
  const cls = v > 30 ? 'red' : v > 10 ? 'yellow' : 'green'
  return <span className={`delta ${cls}`}>{sign}{v.toFixed(1)}%</span>
}

function Links({ prices }) {
  if (!prices?.length) return <span className="muted">—</span>
  return (
    <div className="links">
      {prices.map((p, i) => (
        <a key={i} href={p.url} target="_blank" rel="noreferrer" title={`${p.title} • conf ${p.confidence?.toFixed(2)}`}>
          {p.source || 'ссылка'}
        </a>
      ))}
    </div>
  )
}

function Row({ r, fmt, flagLabel }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <tr className={`row-${r.flag}`}>
        <td className="name">
          <button className="expand" onClick={() => setOpen((o) => !o)}>{open ? '▾' : '▸'}</button>
          {r.item.name}
        </td>
        <td className="num">{fmt(r.item.qty)} {r.item.unit || ''}</td>
        <td className="num">{fmt(r.kp_unit_price)}</td>
        <td className="num">{fmt(r.market_min)}</td>
        <td className="num">{fmt(r.market_median)}</td>
        <td className="num"><Delta v={r.delta_pct} /></td>
        <td><span className={`flag ${r.flag}`}>{flagLabel(r.flag)}</span></td>
        <td><Links prices={r.confirmed_prices} /></td>
      </tr>
      {open && (
        <tr className="detail-row">
          <td colSpan={8}>
            <div className="detail">
              <div><strong>·</strong> {r.flag_reason}</div>
              {r.error && <div className="err">{r.error}</div>}
              {r.query && <div><strong>Запрос:</strong> «{r.query.query}» (×{r.query.pack_multiplier})</div>}
              {r.stage_log?.length > 0 && (
                <details>
                  <summary>{r.stage_log.length}</summary>
                  <ul className="stage-log">{r.stage_log.map((s, i) => <li key={i}>{s}</li>)}</ul>
                </details>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default function ItemsTable({ items }) {
  const { t, locale } = useI18n()
  const fmt = (n) => (n == null ? '—' : new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(n))
  const flagLabel = (f) => t('flag_' + f)
  return (
    <section className="table-wrap">
      <table className="items">
        <thead>
          <tr>
            <th>{t('th_name')}</th>
            <th>{t('th_qty')}</th>
            <th>{t('th_kp_price')}</th>
            <th>{t('th_market_min')}</th>
            <th>{t('th_median')}</th>
            <th>{t('th_delta')}</th>
            <th>{t('th_flag')}</th>
            <th>{t('th_links')}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r, i) => <Row key={i} r={r} fmt={fmt} flagLabel={flagLabel} />)}
        </tbody>
      </table>
    </section>
  )
}
