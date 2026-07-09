import React, { useState } from 'react'

function fmt(n) {
  if (n == null) return '—'
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(n)
}

const FLAG_LABEL = { green: 'Норма', yellow: 'Внимание', red: 'Завышение', gray: 'Проверить' }

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

function Row({ r }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <tr className={`row-${r.flag}`}>
        <td className="name">
          <button className="expand" onClick={() => setOpen((o) => !o)} title="Детали этапов">
            {open ? '▾' : '▸'}
          </button>
          {r.item.name}
        </td>
        <td className="num">{fmt(r.item.qty)} {r.item.unit || ''}</td>
        <td className="num">{fmt(r.kp_unit_price)}</td>
        <td className="num">{fmt(r.market_min)}</td>
        <td className="num">{fmt(r.market_median)}</td>
        <td className="num"><Delta v={r.delta_pct} /></td>
        <td>
          <span className={`flag ${r.flag}`}>{FLAG_LABEL[r.flag] || r.flag}</span>
        </td>
        <td><Links prices={r.confirmed_prices} /></td>
      </tr>
      {open && (
        <tr className="detail-row">
          <td colSpan={8}>
            <div className="detail">
              <div><strong>Решение:</strong> {r.flag_reason}</div>
              {r.error && <div className="err">Ошибка: {r.error}</div>}
              {r.query && (
                <div><strong>Запрос:</strong> «{r.query.query}» (множитель ×{r.query.pack_multiplier})</div>
              )}
              {r.avg_confidence != null && (
                <div><strong>Ср. confidence:</strong> {r.avg_confidence.toFixed(2)}</div>
              )}
              {r.stage_log?.length > 0 && (
                <details>
                  <summary>Лог этапов ({r.stage_log.length})</summary>
                  <ul className="stage-log">
                    {r.stage_log.map((s, i) => <li key={i}>{s}</li>)}
                  </ul>
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
  return (
    <section className="table-wrap">
      <table className="items">
        <thead>
          <tr>
            <th>Наименование</th>
            <th>Кол-во</th>
            <th>Цена КП</th>
            <th>Мин рынка</th>
            <th>Медиана</th>
            <th>Дельта %</th>
            <th>Флаг</th>
            <th>Ссылки</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r, i) => <Row key={i} r={r} />)}
        </tbody>
      </table>
    </section>
  )
}
