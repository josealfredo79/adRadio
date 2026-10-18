import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, it, expect, vi } from 'vitest'
import api from '@/lib/api'
import OrdersPage from '@/pages/OrdersPage'
import LoyaltyContactButton from '@/components/LoyaltyContactButton'

// docs/specs/2026-10-17-cobre.md — monto al confirmar pedidos (caso 8) y "Cobré" en la tarjeta del cliente (caso 1).
vi.mock('@/lib/api', () => ({
  default: { get: vi.fn(() => new Promise(() => {})), post: vi.fn(), patch: vi.fn() },
  getApiError: (_e: unknown, fallback: string) => fallback,
}))
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { payment_link: null, payment_transfer: null, loyalty_config: { enabled: true } },
    setUser: vi.fn(),
    loading: false,
  }),
}))

function wrap(ui: React.ReactNode, qc: QueryClient) {
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <BrowserRouter>{ui}</BrowserRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

beforeEach(() => {
  vi.mocked(api.post).mockReset()
  vi.mocked(api.patch).mockReset().mockResolvedValue({ data: {} })
})

describe('Pedidos — monto al confirmar', () => {
  function renderOrders() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
    qc.setQueryData(['orders', ''], {
      items: [{ id: 'o2', order_number: 'ORD-002', state: 'collecting_payment', items_raw: 'Tamales', customer_name: 'Ana',
        customer_phone: '+529876543210', delivery_address: null, payment_method: null, confirmed_at: null,
        created_at: '2025-01-02T10:00:00Z' }],
      total: 1,
    })
    wrap(<OrdersPage />, qc)
    fireEvent.click(screen.getByText('#ORD-002'))
  }

  it('caso 8: sends the amount when the owner writes it', async () => {
    renderOrders()
    fireEvent.change(screen.getByLabelText('Monto del pedido #ORD-002'), { target: { value: '230' } })
    fireEvent.click(screen.getByText('Confirmar pedido'))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/orders/o2/state', { state: 'confirmed', amount: '230' }))
  })

  it('caso 8: confirming without amount works like before', async () => {
    renderOrders()
    fireEvent.click(screen.getByText('Confirmar pedido'))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/orders/o2/state', { state: 'confirmed' }))
  })
})

describe('Contactos — Cobré en la tarjeta del cliente', () => {
  it('caso 1: charges the customer from their loyalty card', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { amount: 85 } })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
    qc.setQueryData(['contact-loyalty', 'c1'], {
      card: { stamps: 1, required: 5, reward: 'Un kilo gratis', rewards_ready: 0, history: [] },
    })
    wrap(<LoyaltyContactButton contactId="c1" contactName="Ana" className="" />, qc)
    fireEvent.click(screen.getByLabelText('Tarjeta de lealtad de Ana'))
    fireEvent.change(screen.getByLabelText('Monto cobrado a Ana'), { target: { value: '85' } })
    fireEvent.click(screen.getByText('Cobré'))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sales', { amount: '85', contact_id: 'c1' }))
    expect(await screen.findByText(/Cobro de \$85 guardado/)).toBeDefined()
  })
})
