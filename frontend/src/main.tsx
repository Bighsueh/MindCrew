import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { router } from './routes'
import './index.css'
import './styles/zones.css'
import { applyAnimationLevel } from './lib/animationCapability'

// Spec 13: 偵測裝置動畫能力，掛上 [data-anim] root attribute
applyAnimationLevel()

const root = document.getElementById('root')
if (!root) throw new Error('Root element not found')

createRoot(root).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
