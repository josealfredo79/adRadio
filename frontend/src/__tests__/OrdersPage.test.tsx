import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import OrdersPage from '@/pages/OrdersPage'

// PaymentInfoCard (cómo te pagan) lee la sesión.
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { payment_link: null, payment_transfer: null }, setUser: vi.fn(), loading: false }),
}))

const mockOrdersPage = {
  items: [
    { id: '1', order_number: 'ORD-001', state: 'confirmed', items_raw: 'Pizza + Refresco', customer_name: 'Carlos Ruiz', customer_phone: '+521234567890', delivery_address: 'Av. Reforma 123', payment_method: 'tarjeta', confirmed_at: '2025-01-01T12:00:00Z', created_at: '2025-01-01T11:00:00Z', customer_wa_link: 'https://wa.me/521234567890?text=Hola' },
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

describe('OrdersPage — cancelar un pedido ya confirmado', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('pide confirmación y manda el pedido a cancelado', async () => {
    const { fireEvent, waitFor } = await import('@testing-library/react')
    const api = (await import('@/lib/api')).default
    const patch = vi.spyOn(api, 'patch').mockResolvedValue({ data: {} })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()
    fireEvent.click(screen.getByText('#ORD-001'))
    fireEvent.click(screen.getByText('Cancelar pedido'))
    await waitFor(() => expect(patch).toHaveBeenCalledWith('/orders/1/state', { state: 'cancelled' }))
  })

  it('no cancela si el dueño dice que no', async () => {
    const { fireEvent } = await import('@testing-library/react')
    const api = (await import('@/lib/api')).default
    const patch = vi.spyOn(api, 'patch').mockResolvedValue({ data: {} })
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderPage()
    fireEvent.click(screen.getByText('#ORD-001'))
    fireEvent.click(screen.getByText('Cancelar pedido'))
    expect(patch).not.toHaveBeenCalled()
  })

  it('caso4: el pedido enviado trae el botón "Escribirle al cliente" con su link de WhatsApp', () => {
    renderPage()
    fireEvent.click(screen.getByText('#ORD-001'))
    const link = screen.getByRole('link', { name: /Escribirle al cliente/ })
    expect(link.getAttribute('href')).toBe('https://wa.me/521234567890?text=Hola')
    expect(link.getAttribute('target')).toBe('_blank')
  })
})
