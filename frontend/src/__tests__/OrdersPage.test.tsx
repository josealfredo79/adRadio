import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import OrdersPage from '@/pages/OrdersPage'

const mockOrdersPage = {
  items: [
    { id: '1', order_number: 'ORD-001', state: 'confirmed', items_raw: 'Pizza + Refresco', customer_name: 'Carlos Ruiz', customer_phone: '+521234567890', delivery_address: 'Av. Reforma 123', payment_method: 'tarjeta', confirmed_at: '2025-01-01T12:00:00Z', created_at: '2025-01-01T11:00:00Z' },
    { id: '2', order_number: 'ORD-002', state: 'collecting_payment', items_raw: 'Hamburguesa + Papas', customer_name: 'Ana García', customer_phone: '+529876543210', delivery_address: null, payment_method: null, confirmed_at: null, created_at: '2025-01-02T10:00:00Z' },
  ],
  total: 2,
}

function setupQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  })
}

function renderPage() {
  const queryClient = setupQueryClient()
  queryClient.setQueryData(['orders', ''], mockOrdersPage)
  return {
    queryClient,
    ...render(
      <HelmetProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter><OrdersPage /></BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    ),
  }
}

describe('OrdersPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders page title', () => {
    renderPage()
    expect(screen.getByText('Pedidos')).toBeDefined()
  })

  it('renders order numbers', () => {
    renderPage()
    expect(screen.getByText('#ORD-001')).toBeDefined()
    expect(screen.getByText('#ORD-002')).toBeDefined()
  })

  it('renders customer names', () => {
    renderPage()
    expect(screen.getByText((c) => c.includes('Carlos Ruiz'))).toBeDefined()
    expect(screen.getByText((c) => c.includes('Ana García'))).toBeDefined()
  })

  it('renders status badges', () => {
    renderPage()
    expect(screen.getByText('Confirmado')).toBeDefined()
    expect(screen.getByText('Recabando pago')).toBeDefined()
  })

  it('renders search input', () => {
    renderPage()
    const search = screen.getByPlaceholderText('Buscar por número, cliente, teléfono...')
    expect(search).toBeDefined()
  })

  it('renders filter buttons', () => {
    renderPage()
    expect(screen.getByText('Todos')).toBeDefined()
    expect(screen.getAllByText('Confirmados')[0]).toBeDefined()
    expect(screen.getByText('Pendientes de pago')).toBeDefined()
  })

  it('renders PrintButton', () => {
    renderPage()
    expect(screen.getByText('Imprimir / PDF')).toBeDefined()
  })
})
