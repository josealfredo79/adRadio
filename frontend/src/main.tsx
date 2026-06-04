import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'
import { ThemeProvider } from '@/contexts/ThemeContext'
import { ToastProvider } from '@/contexts/ToastContext'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import CookieConsent from './components/CookieConsent'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,
      retry: 1,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <HelmetProvider>
      <ErrorBoundary>
        <ThemeProvider>
          <QueryClientProvider client={queryClient}>
            <ToastProvider>
              <App />
              <CookieConsent />
            </ToastProvider>
          </QueryClientProvider>
        </ThemeProvider>
      </ErrorBoundary>
    </HelmetProvider>
  </React.StrictMode>
)
