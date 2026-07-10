import React from 'react'
import { useI18n } from '../i18n.jsx'

export default function Summary({ summary }) {
  const { t, locale } = useI18n()
  const fmt = (n) => (n == null ? '—' : new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(n))
  const cards = [
    { key: 'green', label: t('sum_green'), val: summary.green },
    { key: 'yellow', label: t('sum_yellow'), val: summary.yellow },
    { key: 'red', label: t('sum_red'), val: summary.red },
    { key: 'gray', label: t('sum_gray'), val: summary.gray },
  ]
  return (
    <section className="summary">
      <div className="summary-cards">
        {cards.map((c) => (
          <div key={c.key} className={`sum-card ${c.key}`}>
            <div className="sum-num">{c.val}</div>
            <div className="sum-lbl">{c.label}</div>
          </div>
        ))}
      </div>
      <div className="summary-overpay">
        <span>{t('sum_overpay')}</span>
        <strong>
          {fmt(summary.estimated_total_overpay)} {summary.currency}
        </strong>
      </div>
    </section>
  )
}
