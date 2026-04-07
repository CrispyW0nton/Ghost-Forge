import { resolve } from 'path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()]
  },
  preload: {
    plugins: [externalizeDepsPlugin()]
  },
  renderer: {
    resolve: {
      alias: {
        '@renderer': resolve('src/renderer/src'),
        '@components': resolve('src/renderer/src/components'),
        '@store': resolve('src/renderer/src/store'),
        '@hooks': resolve('src/renderer/src/hooks'),
        '@modules': resolve('src/renderer/src/modules')
      }
    },
    plugins: [react()],
    css: {
      postcss: './postcss.config.js'
    }
  }
})
