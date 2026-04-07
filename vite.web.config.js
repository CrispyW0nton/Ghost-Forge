import { resolve } from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Web-only preview config (no Electron)
export default defineConfig({
  root: 'src/renderer',
  resolve: {
    alias: {
      '@renderer':   resolve('src/renderer/src'),
      '@components': resolve('src/renderer/src/components'),
      '@store':      resolve('src/renderer/src/store'),
      '@hooks':      resolve('src/renderer/src/hooks'),
      '@modules':    resolve('src/renderer/src/modules'),
    }
  },
  plugins: [react()],
  css: {
    postcss: '../../postcss.config.js'
  },
  server: {
    port: 3001,
    strictPort: false,
    host: '0.0.0.0',
    proxy: {
      // Proxy all /api/* requests to the Flask backend
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        rewrite: (path) => path,
      }
    },
    // Allow cross-origin requests from sandbox URLs
    cors: true,
  },
  // Optimise large Three.js deps
  optimizeDeps: {
    include: [
      'three',
      '@react-three/fiber',
      '@react-three/drei',
      'three/examples/jsm/loaders/OBJLoader.js',
      'three/examples/jsm/loaders/STLLoader.js',
      'three/examples/jsm/loaders/PLYLoader.js',
    ]
  }
})
