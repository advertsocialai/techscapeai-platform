import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from './lib/auth.tsx'
import { ErrorBoundary } from './components/ErrorBoundary'
import { initErrorReporting } from './lib/errorReporting'

// Window-level capture (unhandled errors + promise rejections). This existed
// in lib/errorReporting.ts but was never called here — the classic
// exists-but-unwired failure mode; wired 2026-08-10.
initErrorReporting()

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* One boundary above the router root: render errors anywhere in the app
        report into errorReporting and show a recovery screen, never a blank
        page. window listeners alone cannot catch these. */}
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
          {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
