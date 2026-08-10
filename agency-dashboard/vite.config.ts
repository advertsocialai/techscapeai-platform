/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    // Component tests (Testing Library) need a DOM; the pure-unit suites are
    // environment-agnostic and run fine under jsdom too. `globals` is what
    // lets Testing Library register its afterEach auto-cleanup — without it,
    // renders leak across tests and every getBy* finds duplicates.
    environment: 'jsdom',
    globals: true,
  },
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      // The live call feed is mounted at the app ROOT (`/ws/calls/{id}`), not
      // under `/api` — see api/app/main.py. Without this entry a same-origin
      // WebSocket from :5174 never reaches the API on :8000, and the live-call
      // screen silently shows "reconnecting" forever. `ws: true` is what makes
      // Vite proxy the HTTP Upgrade handshake rather than treating it as a
      // normal request. Fixes DEBT-14.
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
