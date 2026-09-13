import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Frontend is a separate deployable; dev server proxies /api to the backend
// so the browser talks to one origin. Override backend via VITE_API_TARGET.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5273,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8700',
        changeOrigin: true,
      },
    },
  },
})
