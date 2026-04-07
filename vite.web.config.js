import { resolve } from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Web-only build config (no Electron) for browser preview
export default defineConfig({
  root: 'src/renderer',
  resolve: {
    alias: {
      '@renderer': resolve('src/renderer/src'),
      '@components': resolve('src/renderer/src/components'),
      '@store': resolve('src/renderer/src/store'),
      '@hooks': resolve('src/renderer/src/hooks'),
      '@modules': resolve('src/renderer/src/modules'),
    }
  },
  plugins: [react()],
  css: {
    postcss: '../../postcss.config.js'
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': 'http://localhost:5000'
    }
  }
})
