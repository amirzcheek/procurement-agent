import React, { useEffect, useState } from 'react'
import { getEmployees } from '../api.js'
import { useI18n } from '../i18n.jsx'
import PeriodSelector from './PeriodSelector.jsx'

export default function EmployeesView({ dbEnabled, selfOnly }) {
  const { t } = useI18n()
  const [period, setPeriod] = useState({ months: 12 })
  const [rows, setRows] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!dbEnabled) return
    getEmployees(period).then((d) => setRows(d.employees || [])).catch((e) => setError(String(e.message || e)))
  }, [dbEnabled, period])

  if (!dbEnabled) return <div className="notice">{t('hist_disabled')}</div>

  return (
    <div>
      <h2 className="page-title">{selfOnly ? t('tab_my_stats') : t('tab_employees')}</h2>
      {/* Обязательный дисклеймер прямо из ТЗ */}
      <div className="disclaimer">⚠️ {t('emp_disclaimer')}</div>
      <PeriodSelector value={period} onChange={setPeriod} />
      {error && <div className="error">{t('err_prefix')}: {error}</div>}
      <div className="table-wrap">
        <table className="items">
          <thead>
            <tr>
              <th>{t('a_user')}</th><th>{t('emp_uploads')}</th><th>{t('emp_checks')}</th>
              <th>{t('emp_confirms')}</th><th>{t('emp_avg_hours')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="name">{r.email}</td>
                <td className="num">{r.uploads}</td>
                <td className="num">{r.checks}</td>
                <td className="num">{r.confirms}</td>
                <td className="num">{r.avg_hours_to_confirm ?? '—'}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={5} className="muted">—</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
