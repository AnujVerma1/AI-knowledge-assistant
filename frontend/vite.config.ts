import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // BACKEND_URL has no VITE_ prefix, so it is only used here and never exposed to the browser.
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      strictPort: true,
      // The dev server forwards /api to FastAPI. The browser sees a single origin, so the
      // HttpOnly session cookie works exactly as it will behind Vercel's /api rewrite.
      proxy: {
        '/api': { target: env.BACKEND_URL || 'http://127.0.0.1:8001' },
      },
    },
  }
})
