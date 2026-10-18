import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { beforeEach, describe, it, expect, vi } from 'vitest'
import api from '@/lib/api'
import CashierPage from '@/pages/CashierPage'

// docs/specs/2026-10-17-cobre.md — la pantalla "Cobrar" del dueño.
vi.mock('@/lib/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  getApiError: (e: { response?: { data?: { detail?: string } } }, fallback: string) =>
    e?.response?.data?.detail ?? fallback,
}))

const ana = { id: 'c1', name: 'Ana López', phone_last4: '1234' }

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <CashierPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

beforeEach(() => {
  vi.mocked(api.get).mockReset().mockImplementation((url: string) =>
    Promise.resolve({
      data:
        url === '/sales/today' ? { count: 0, total: 0 }
        : url === '/sales/shortcuts' ? { amounts: [20, 35, 50, 100], recent: [{ id: 'c7', name: 'Beto Ruiz', phone_last4: '5678' }] }
        : [ana],
    }),
  )
  vi.mocked(api.post).mockReset()
  vi.mocked(api.delete).mockReset()
})

describe('CashierPage', () => {
  it('caso 1: finds the customer by last digits, charges and shows the stamp and today total', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { id: 's1', amount: 85, customer: ana, stamped: true, today: { count: 1, total: 85 } },
    })
    renderPage()
    fireEvent.change(screen.getByLabelText('Monto cobrado'), { target: { value: '85' } })
    fireEvent.change(screen.getByLabelText('Buscar cliente'), { target: { value: '1234' } })
    fireEvent.click(await screen.findByText('Ana López'))
    fireEvent.click(screen.getByText('Cobré $85'))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sales', { amount: '85', contact_id: 'c1' }))
    expect(await screen.findByText(/\+1 sello/)).toBeDefined()
    expect(screen.getByText(/Hoy llevas/).textContent).toMatch(/85\.00.*1 venta$/)
  })

  it('caso 3: new customer sends name and phone', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { id: 's2', amount: 120, customer: { id: 'c9', name: 'Mari', phone_last4: '5555' }, stamped: true, today: { count: 1, total: 120 } },
    })
    renderPage()
    fireEvent.change(screen.getByLabelText('Monto cobrado'), { target: { value: '120' } })
    fireEvent.click(screen.getByText('Cliente nuevo'))
    expect((screen.getByText('Cobré $120') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Nombre del cliente'), { target: { value: 'Mari' } })
    fireEvent.change(screen.getByLabelText('Teléfono del cliente'), { target: { value: '9531234567' } })
    fireEvent.click(screen.getByText('Cobré $120'))
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/sales', { amount: '120', new_customer: { name: 'Mari', phone: '9531234567' } }),
    )
  })

  it('caso 4: sale without customer sends only the amount', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { id: 's3', amount: 40, customer: null, stamped: false, today: { count: 1, total: 40 } },
    })
    renderPage()
    fireEvent.change(screen.getByLabelText('Monto cobrado'), { target: { value: '40' } })
    fireEvent.click(screen.getByText('Sin cliente'))
    fireEvent.click(screen.getByText('Cobré $40'))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sales', { amount: '40' }))
    expect(await screen.findByText(/Cobraste/)).toBeDefined()
    expect(screen.queryByText(/\+1 sello/)).toBeNull()
  })

  it('caso 5: the reason for a bad amount is shown', async () => {
    vi.mocked(api.post).mockRejectedValue({ response: { data: { detail: 'El monto debe ser mayor a $0' } } })
    renderPage()
    fireEvent.change(screen.getByLabelText('Monto cobrado'), { target: { value: '0' } })
    fireEvent.click(screen.getByText('Sin cliente'))
    fireEvent.click(screen.getByText('Cobré $0'))
    expect(await screen.findByText('El monto debe ser mayor a $0')).toBeDefined()
  })

  it('caso 6: the last charge can be undone', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { id: 's4', amount: 85, customer: ana, stamped: true, today: { count: 1, total: 85 } },
    })
    vi.mocked(api.delete).mockResolvedValue({ data: { today: { count: 0, total: 0 } } })
    renderPage()
    fireEvent.change(screen.getByLabelText('Monto cobrado'), { target: { value: '85' } })
    fireEvent.click(screen.getByText('Sin cliente'))
    fireEvent.click(screen.getByText('Cobré $85'))
    fireEvent.click(await screen.findByText('Deshacer'))
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/sales/s4'))
    await waitFor(() => expect(screen.queryByText(/Cobraste/)).toBeNull())
    expect(screen.getByText(/Hoy llevas/).textContent).toMatch(/0 ventas$/)
  })

  it('needs an amount and who before enabling the button', () => {
    renderPage()
    expect((screen.getByText('Cobré') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Monto cobrado'), { target: { value: '10' } })
    expect((screen.getByText('Cobré $10') as HTMLButtonElement).disabled).toBe(true)
  })

  it('caso 8 (copiloto): a quick amount fills the amount with one tap', async () => {
    renderPage()
    fireEvent.click(await screen.findByText('$35'))
    expect((screen.getByLabelText('Monto cobrado') as HTMLInputElement).value).toBe('35')
    expect(screen.getByText('Cobré $35')).toBeDefined()
  })

  it('caso 9 (copiloto): a recent customer is picked without searching', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { id: 's5', amount: 35, customer: { id: 'c7', name: 'Beto Ruiz', phone_last4: '5678' }, stamped: true, today: { count: 1, total: 35 } },
    })
    renderPage()
    fireEvent.click(await screen.findByText('$35'))
    fireEvent.click(await screen.findByText('Beto Ruiz'))
    fireEvent.click(screen.getByText('Cobré $35'))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sales', { amount: '35', contact_id: 'c7' }))
  })
})
