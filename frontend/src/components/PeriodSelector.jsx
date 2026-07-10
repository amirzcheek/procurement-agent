import React from 'react'
import { useI18n } from '../i18n.jsx'

// Селектор периода сравнения цен: пресеты + свой диапазон.
// value: { months: number|null, dateFrom?: string, dateTo?: string }
export default function PeriodSelector({ value, onChange }) {
  const { t } = useI18n()
  const presets = [
    { key: 3, label: t('p_3m') },
    { key: 6, label: t('p_6m') },
    { key: 12, label: t('p_12m') },
    { key: 0, label: t('p_all') },
  ]
  const isCustom = value.months == null

  return (
    <div className="period">
      <span className="period-label">{t('period_title')}:</span>
      <div className="period-presets">
        {presets.map((p) => (
          <button
            key={p.key}
            className={'chip' + (!isCustom && value.months === p.key ? ' active' : '')}
            onClick={() => onChange({ months: p.key })}
          >
            {p.label}
          </button>
        ))}
        <button
          className={'chip' + (isCustom ? ' active' : '')}
          onClick={() =>
            onChange({ months: null, dateFrom: value.dateFrom || '', dateTo: value.dateTo || '' })
          }
        >
          {t('p_custom')}
        </button>
      </div>
      {isCustom && (
        <div className="period-range">
          <label>
            {t('date_from')}
            <input
              type="date"
              value={value.dateFrom || ''}
              onChange={(e) => onChange({ ...value, months: null, dateFrom: e.target.value })}
            />
          </label>
          <label>
            {t('date_to')}
            <input
              type="date"
              value={value.dateTo || ''}
              onChange={(e) => onChange({ ...value, months: null, dateTo: e.target.value })}
            />
          </label>
        </div>
      )}
    </div>
  )
}
