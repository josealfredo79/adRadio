import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect } from 'vitest'
import { ToastProvider } from '@/contexts/ToastContext'
import PlansPage from '@/pages/PlansPage'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: '1', email: 'test@test.com' }, loading: false }),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <HelmetProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter><ToastProvider>{children}</ToastProvider></BrowserRouter>
      </QueryClientProvider>
    </HelmetProvider>
  )
}

describe('PlansPage', () => {
  it('renders plan cards', () => {
    render(<PlansPage />, { wrapper: Wrapper })
    expect(screen.getByText('Starter')).toBeDefined()
    expect(screen.getByText('Growth')).toBeDefined()
    expect(screen.getByText('Pro')).toBeDefined()
  })

  it('renders pricing info', () => {
    render(<PlansPage />, { wrapper: Wrapper })
    const prices = screen.getAllByText(/\$/)
    expect(prices.length).toBeGreaterThanOrEqual(3)
  })
})
