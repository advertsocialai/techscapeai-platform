import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/global.css'
import App from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import { initErrorReporting } from './lib/errorReporting'

initErrorReporting()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* One boundary above the router root: render errors anywhere in the app
        report into errorReporting and show a recovery screen, never a blank
        page. window listeners alone cannot catch these. */}
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
)
