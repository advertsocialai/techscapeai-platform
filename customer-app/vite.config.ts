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
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      }
    }
  }
})