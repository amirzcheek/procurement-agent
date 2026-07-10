import React from 'react'

import { useI18n, LangSwitcher } from '../i18n.jsx'
import { useSession } from '../auth/useSession.js'

const PORTAL = import.meta.env.VITE_PORTAL_URL ?? 'https://ai.knus.edu.kz'

// Навбар портала ai.knus.edu.kz. Имя/роль/«Админка» — из сессии платформы.
export default function Navbar() {
  const { t } = useI18n()
  const { user } = useSession()

  return (
    <header className="topbar">
      <div className="topbar-left">
        <a className="brand" href={`${PORTAL}/`}>
          KNUS Digital
        </a>
        <span className="brand-sep">/</span>
        <span className="brand-agent">{t('agent_name')}</span>
        <LangSwitcher />
      </div>

      <div className="topbar-right">
        {user.displayName && <span className="user-name">{user.displayName}</span>}
        {user.role && <span className="role-badge">{user.role}</span>}
        {user.isAdmin && (
          <a className="admin-link" href={`${PORTAL}/admin`}>
            {t('admin')}
          </a>
        )}
        <a className="logout-btn" href={`${PORTAL}/`}>
          {t('to_portal')}
        </a>
      </div>
    </header>
  )
}
