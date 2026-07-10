import React from 'react'
import { useI18n } from '../i18n.jsx'

const RISK_CLASS = { low: 'green', medium: 'yellow', high: 'red', unknown: 'gray' }

function fmt(n, locale) {
  if (n == null) return '—'
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(n)
}

function Sparkline({ points }) {
  const pts = (points || []).filter((p) => p.date).sort((a, b) => a.date.localeCompare(b.date))
  if (pts.length < 2) return null
  const w = 90
  const h = 24
  const prices = pts.map((p) => p.price)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const span = max - min || 1
  const d = pts
    .map((p, i) => {
      const x = (i / (pts.length - 1)) * w
      const y = h - ((p.price - min) / span) * h
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

function Trend({ stats }) {
  const { t } = useI18n()
  if (!stats || !stats.trend_direction) return <span className="muted">—</span>
  const dir = stats.trend_direction
  const arrow = dir === 'rising' ? '▲' : dir === 'falling' ? '▼' : '▬'
  const cls = dir === 'rising' ? 'red' : dir === 'falling' ? 'green' : ''
  const label = dir === 'rising' ? t('trend_rising') : dir === 'falling' ? t('trend_falling') : t('trend_flat')
  return (
    <span className="trend">
      <Sparkline points={stats.points} />
      <span className={`trend-tag ${cls}`}>
        {arrow} {label} {stats.trend_pct != null ? `${stats.trend_pct > 0 ? '+' : ''}${stats.trend_pct}%` : ''}
      </span>
    </span>
  )
}

function SourceCell({ stats, locale }) {
  const { t } = useI18n()
  if (!stats || !stats.count) return <span className="muted">—</span>
  return (
    <span>
      {fmt(stats.min, locale)} – {fmt(stats.max, locale)}{' '}
      <small className="muted">({stats.count})</small>
    </span>
  )
}

export default function HistoricalPanel({ historical, loading }) {
  const { t, locale } = useI18n()
  if (loading) return <p className="muted">{t('hist_loading')}</p>
  if (!historical) return null
  if (historical.enabled === false) return <div className="notice">{t('hist_disabled')}</div>
  const items = historical.items || []
  if (!items.length) return null

  return (
    <section className="hist">
      <h3 className="section-title">
        {t('hist_title')} <span className="muted">· {historical.period_label}</span>
      </h3>
      <div className="table-wrap">
        <table className="items">
          <thead>
            <tr>
              <th>{t('th_name')}</th>
              <th>{t('th_kp_price')}</th>
              <th>{t('hist_internal')}</th>
              <th>{t('hist_web')}</th>
              <th>{t('hist_trend')}</th>
              <th>{t('hist_risk')}</th>
              <th>{t('hist_reco')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, i) => {
              const rc = RISK_CLASS[it.risk_level] || 'gray'
              return (
                <tr key={i} className={`row-${rc}`}>
                  <td className="name">{it.name}</td>
                  <td className="num">{fmt(it.kp_unit_price, locale)}</td>
                  <td><SourceCell stats={it.internal} locale={locale} /></td>
                  <td><SourceCell stats={it.web} locale={locale} /></td>
                  <td><Trend stats={it.web && it.web.count ? it.web : it.internal} /></td>
                  <td>
                    <span className={`flag ${rc}`}>{t('risk_' + (it.risk_level || 'unknown'))}</span>
                  </td>
                  <td className="reco">{it.recommendation || it.message || ''}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
