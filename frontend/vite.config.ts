import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import vuetify from 'vite-plugin-vuetify'
import { configDefaults } from 'vitest/config'

// In development the API runs on uvicorn; nginx does this proxying in production.
const apiTarget = process.env.ARESGATE_API_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue(), vuetify({ autoImport: true })],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: apiTarget, changeOrigin: true } },
  },
  // The end-to-end tests that run without a container serve the built app with `vite preview`.
  preview: {
    host: '127.0.0.1',
    proxy: { '/api': { target: apiTarget, changeOrigin: true } },
  },
  build: {
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    // Every test file gets a fresh worker and jsdom, so nothing one leaves behind reaches the
    // next, and CI transforms the code afresh on every run. Naming these choices keeps Vitest from
    // printing hints about trading that isolation for speed.
    pool: 'forks',
    isolate: true,
    fsModuleCache: false,
    setupFiles: ['src/test/setup.ts'],
    // Playwright runs the end-to-end tests in e2e/ (npm run e2e).
    exclude: [...configDefaults.exclude, 'e2e/**'],
    server: { deps: { inline: ['vuetify'] } },
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,vue}'],
      exclude: ['src/**/*.spec.ts', 'src/test/**'],
      // lcov.info names files from the repository root (frontend/src/…), as SonarQube expects.
      reporter: ['text', ['lcovonly', { projectRoot: '..' }], 'html'],
      thresholds: { lines: 95, functions: 95, branches: 95, statements: 95 },
    },
  },
})
