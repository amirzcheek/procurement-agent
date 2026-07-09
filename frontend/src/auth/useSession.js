import { useEffect, useState } from 'react'

import { API_BASE } from '../api.js'

// Хук сессии пользователя. Авторизацию делает платформа на уровне Caddy
// (forward_auth). Наш backend под слагом отдаёт GET <слаг>/auth/session
//   { user: { displayName, isAdmin } }
// на основе заголовков, которые платформа прокидывает после авторизации.
// Нет данных — graceful fallback на «гостя». Для превью админ-вида в dev:
// VITE_PREVIEW_ADMIN=true.
const FALLBACK_USER = {
  displayName: '',
  isAdmin: import.meta.env.VITE_PREVIEW_ADMIN === 'true',
}

export function useSession() {
  const [user, setUser] = useState(FALLBACK_USER)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    fetch(`${API_BASE}/auth/session`, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (active && data && data.user) setUser(data.user)
      })
      .catch(() => {
        /* нет сессии — остаёмся на fallback (гость) */
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  return { user, loading }
}
