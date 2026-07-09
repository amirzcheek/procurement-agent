import React from 'react'

import { useSession } from '../auth/useSession.js'

// Базовый адрес портала (бренд и «Вернуться на портал» ведут туда).
// Переопределяется через VITE_PORTAL_URL, по умолчанию — прод-портал.
const PORTAL = import.meta.env.VITE_PORTAL_URL ?? 'https://ai.knus.edu.kz'

// Навбар портала ai.knus.edu.kz, адаптированный под этого агента.
// Имя пользователя и «Админка» берутся из сессии портала (/auth/session).
export default function Navbar() {
  const { user } = useSession()

  return (
    <header className="topbar">
      <div className="topbar-left">
        <a className="brand" href={`${PORTAL}/`}>
          KNUS Digital
        </a>
        <span className="brand-sep">/</span>
        <span className="brand-agent">Анализатор закупок</span>
      </div>

      <div className="topbar-right">
        {user.displayName && <span className="user-name">{user.displayName}</span>}
        {user.isAdmin && (
          <a className="admin-link" href={`${PORTAL}/admin`}>
            Админка
          </a>
        )}
        <a className="logout-btn" href={`${PORTAL}/`}>
          Вернуться на портал
        </a>
      </div>
    </header>
  )
}
