import React from 'react'

function fmt(n) {
  if (n == null) return '—'
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(n)
}

export default function Summary({ summary }) {
  const cards = [
    { key: 'green', label: 'Норма', cls: 'green', val: summary.green },
    { key: 'yellow', label: 'Внимание', cls: 'yellow', val: summary.yellow },
    { key: 'red', label: 'Завышение', cls: 'red', val: summary.red },
    { key: 'gray', label: 'Проверить', cls: 'gray', val: summary.gray },
  ]
  return (
    <section className="summary">
      <div className="summary-cards">
        {cards.map((c) => (
          <div key={c.key} className={`sum-card ${c.cls}`}>
            <div className="sum-num">{c.val}</div>
            <div className="sum-lbl">{c.label}</div>
          </div>
        ))}
      </div>
      <div className="summary-overpay">
        <span>Оценочная переплата по КП:</span>
        <strong>
          {fmt(summary.estimated_total_overpay)} {summary.currency}
        </strong>
        <small> (по позициям с ценой выше рыночной медианы)</small>
      </div>
    </section>
  )
}
