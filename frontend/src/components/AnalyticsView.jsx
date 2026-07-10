import React, { useEffect, useState } from 'react'
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts'
import { getDashboard, getSuppliers, getSupplierCard, getOffers, getItemHistory } from '../api.js'
import { useI18n } from '../i18n.jsx'
import PeriodSelector from './PeriodSelector.jsx'

const RISK_CLASS = { low: 'green', medium: 'yellow', high: 'red', unknown: 'gray' }
const ACCENT = '#2563eb'
const RED = '#b91c1c'

function Chart({ children, height = 240 }) {
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>{children}</ResponsiveContainer>
    </div>
  )
}

function num(n, locale) {
  return n == null ? '—' : new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(n)
}

// ── Панель ───────────────────────────────────────────────────────────────────
function DashboardPanel({ period }) {
  const { t, locale } = useI18n()
  const [d, setD] = useState(null)
  useEffect(() => { getDashboard(period).then(setD).catch(() => setD(null)) }, [period])
  if (!d) return <p className="muted">…</p>

  return (
    <div>
      <div className="summary-cards">
        <div className="sum-card"><div className="sum-num">{d.contracts_total}</div><div className="sum-lbl">{t('dash_total')}</div></div>
        <div className="sum-card green"><div className="sum-num">{d.contracts_checked}</div><div className="sum-lbl">{t('dash_checked')}</div></div>
        <div className="sum-card red"><div className="sum-num">{d.high_risk}</div><div className="sum-lbl">{t('dash_high')}</div></div>
        <div className="sum-card"><div className="sum-num" style={{ fontSize: 18 }}>{num(d.price_min, locale)}–{num(d.price_max, locale)}</div><div className="sum-lbl">{t('dash_price_range')}</div></div>
      </div>

      <div className="analytics-grid">
        <div className="card">
          <div className="card-title">{t('dash_price_dynamics')}</div>
          <Chart>
            <LineChart data={d.price_dynamics}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="month" fontSize={11} /><YAxis fontSize={11} width={50} />
              <Tooltip />
              <Line type="monotone" dataKey="min" stroke={ACCENT} name={t('chart_min')} dot={false} />
              <Line type="monotone" dataKey="max" stroke={RED} name={t('chart_max')} dot={false} />
            </LineChart>
          </Chart>
        </div>
        <div className="card">
          <div className="card-title">{t('dash_purchases')}</div>
          <Chart>
            <BarChart data={d.purchases_by_month}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="month" fontSize={11} /><YAxis fontSize={11} width={40} allowDecimals={false} />
              <Tooltip /><Bar dataKey="count" fill={ACCENT} name={t('chart_count')} />
            </BarChart>
          </Chart>
        </div>
        <div className="card">
          <div className="card-title">{t('dash_by_category')}</div>
          <Chart>
            <BarChart data={d.by_category} layout="vertical" margin={{ left: 20 }}>
              <XAxis type="number" fontSize={11} allowDecimals={false} />
              <YAxis type="category" dataKey="category" fontSize={11} width={120} />
              <Tooltip /><Bar dataKey="count" fill={ACCENT} />
            </BarChart>
          </Chart>
        </div>
        <div className="card">
          <div className="card-title">{t('dash_deviations')}</div>
          {(d.deviations || []).length === 0 ? <div className="muted">—</div> : (
            <ul className="factors">
              {d.deviations.map((x, i) => <li key={i}>{x.factor} <span className="muted">· {x.count}</span></li>)}
            </ul>
          )}
        </div>
      </div>

      <div className="analytics-grid">
        <div className="card">
          <div className="card-title">{t('dash_supplier_rating')}</div>
          <div className="table-wrap"><table className="items">
            <thead><tr><th>{t('c_supplier')}</th><th>{t('sup_contracts')}</th><th>{t('sup_items')}</th><th>{t('sup_flag_over')}</th></tr></thead>
            <tbody>{(d.supplier_rating || []).map((s) => (
              <tr key={s.id}><td className="name">{s.name || '—'}</td><td className="num">{s.contracts}</td><td className="num">{s.items}</td>
                <td>{s.flag ? <span className="flag red">⚠</span> : '—'}</td></tr>
            ))}</tbody>
          </table></div>
        </div>
        <div className="card">
          <div className="card-title">{t('dash_by_department')}</div>
          <ul className="factors">{(d.by_department || []).map((x, i) => <li key={i}>{x.customer} <span className="muted">· {x.count}</span></li>)}</ul>
        </div>
      </div>
    </div>
  )
}

function SuppliersPanel({ period }) {
  const { t, locale } = useI18n()
  const [list, setList] = useState([])
  const [card, setCard] = useState(null)
  useEffect(() => { getSuppliers(period).then((d) => setList(d.suppliers || [])).catch(() => setList([])) }, [period])

  if (card) {
    return (
      <div>
        <button className="back-link" onClick={() => setCard(null)}>← {t('sub_suppliers')}</button>
        <h3 className="section-title">{card.name}</h3>
        <div className="card">
          <div className="card-title">{t('sup_price_dynamics')}</div>
          <Chart>
            <LineChart data={card.price_series}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" fontSize={11} /><YAxis fontSize={11} width={50} />
              <Tooltip /><Line type="monotone" dataKey="price" stroke={ACCENT} dot={false} />
            </LineChart>
          </Chart>
        </div>
        <h4 className="section-title" style={{ fontSize: 14 }}>{t('sup_products')}</h4>
        <ul className="factors">{(card.products || []).map((p, i) => <li key={i}>{p.canonical} <span className="muted">· {p.count}</span></li>)}</ul>
      </div>
    )
  }

  return (
    <div className="table-wrap"><table className="items">
      <thead><tr><th>{t('c_supplier')}</th><th>{t('sup_contracts')}</th><th>{t('sup_items')}</th><th>{t('hist_min')}</th><th>{t('hist_max')}</th><th>{t('sup_flag_over')}</th></tr></thead>
      <tbody>{list.map((s) => (
        <tr key={s.id} className="clickable" onClick={() => getSupplierCard(s.id).then(setCard)}>
          <td className="name">{s.name || '—'}</td><td className="num">{s.contracts}</td><td className="num">{s.items}</td>
          <td className="num">{num(s.min_price, locale)}</td><td className="num">{num(s.max_price, locale)}</td>
          <td>{s.flag ? <span className="flag red">⚠ {Math.round(s.over_share * 100)}%</span> : '—'}</td>
        </tr>
      ))}</tbody>
    </table></div>
  )
}

function OffersPanel({ period }) {
  const { t, locale } = useI18n()
  const [items, setItems] = useState([])
  const [hist, setHist] = useState(null)
  useEffect(() => { getOffers(period).then((d) => setItems(d.items || [])).catch(() => setItems([])) }, [period])

  return (
    <div>
      {hist && (
        <div className="card">
          <div className="card-title">{hist.canonical}</div>
          <Chart>
            <LineChart data={hist.series}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" fontSize={11} /><YAxis fontSize={11} width={50} />
              <Tooltip /><Line type="monotone" dataKey="price" stroke={ACCENT} dot={{ r: 2 }} />
            </LineChart>
          </Chart>
          <button className="back-link" onClick={() => setHist(null)}>×</button>
        </div>
      )}
      <div className="table-wrap"><table className="items">
        <thead><tr><th>{t('th_name')}</th><th>{t('c_supplier')}</th><th>{t('th_kp_price')}</th><th>{t('off_hist_max')}</th><th></th></tr></thead>
        <tbody>{items.map((it, i) => (
          <tr key={i} className={it.in_range === false ? 'row-red' : ''}>
            <td className="name clickable" onClick={() => it.canonical && getItemHistory(it.canonical).then((d) => setHist({ canonical: it.canonical, series: d.series }))}>{it.name}</td>
            <td>{it.supplier || '—'}</td><td className="num">{num(it.price, locale)}</td><td className="num">{num(it.hist_max, locale)}</td>
            <td>{it.in_range === false ? <span className="flag red">{t('off_out_range')}</span> : it.in_range ? <span className="flag green">{t('off_in_range')}</span> : '—'}</td>
          </tr>
        ))}</tbody>
      </table></div>
    </div>
  )
}

export default function AnalyticsView({ dbEnabled }) {
  const { t } = useI18n()
  const [sub, setSub] = useState('dashboard')
  const [period, setPeriod] = useState({ months: 12 })
  if (!dbEnabled) return <div className="notice">{t('hist_disabled')}</div>

  return (
    <div>
      <nav className="tabs sub-tabs">
        {['dashboard', 'suppliers', 'offers'].map((s) => (
          <button key={s} className={'tab' + (sub === s ? ' active' : '')} onClick={() => setSub(s)}>{t('sub_' + s)}</button>
        ))}
      </nav>
      <PeriodSelector value={period} onChange={setPeriod} />
      {sub === 'dashboard' && <DashboardPanel period={period} />}
      {sub === 'suppliers' && <SuppliersPanel period={period} />}
      {sub === 'offers' && <OffersPanel period={period} />}
    </div>
  )
}
