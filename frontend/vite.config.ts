import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

// The dev server proxies /api to the chat backend so the browser sees a single
// origin. That keeps CORS out of the picture in development; in production the
// reverse proxy / ingress is expected to do the same routing.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // Fail loudly instead of silently hopping to 5174 — the port is referenced
    // in CORS_ORIGINS and the README, so a moved dev server breaks auth calls.
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
