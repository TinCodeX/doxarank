import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import Clarity from '@microsoft/clarity'
import './index.css'
import App from './App.tsx'

const clarityProjectId = import.meta.env.VITE_CLARITY_PROJECT_ID;
if (clarityProjectId) {
  Clarity.init(clarityProjectId);
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

