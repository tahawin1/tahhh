import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { API_URL, MODE_DEMO } from './api.ts'

async function demarrer() {
  if (MODE_DEMO) {
    // chargé seulement en démonstration : n'alourdit pas le build normal
    const { installerDemo } = await import('./demo/moteurDemo.ts')
    installerDemo(API_URL!)
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

demarrer()
