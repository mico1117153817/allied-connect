import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { pdfjsAssets } from './vite-pdfjs-assets.js'

export default defineConfig({
  plugins: [react(), pdfjsAssets()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
