import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// PAGE_UNIQUE=1 : tout le code dans un seul fichier JS (modules chargés à la
// demande inclus), pour les pages autonomes (démo et édition claude.ai).
const pageUnique = process.env.PAGE_UNIQUE === '1'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: pageUnique ? { rollupOptions: { output: { inlineDynamicImports: true } } } : {},
})
