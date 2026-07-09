import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base — префикс под-пути на портале. Для сборки под ai.knus.edu.kz/agents/procurement/
// задаётся аргументом VITE_BASE (см. Dockerfile). По умолчанию '/' — для локальной разработки.
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE || '/',
  server: {
    port: 5173,
    // В dev запросы /api/* идут на локальный backend (:8090), CORS не нужен.
    proxy: {
      '/api': {
        target: 'http://localhost:8090',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
