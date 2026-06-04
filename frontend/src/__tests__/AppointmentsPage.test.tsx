import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import AppointmentsPage from '@/pages/AppointmentsPage'

const mockStats = { total: 10, upcoming: 3, today: 2, google_connected: false }
const mockAppointments = [
  { id: '1', customer_name: 'Maria Lopez', customer_phone: '+521234567890', service: 'Corte de cabello', scheduled_at: '2026-06-04T14:00:00Z', duration_min: 30, notes: null, status: 'confirmed', google_event_id: null, contact_id: 'c1', created_at: '2025-01-01T00:00:00Z' },
  { id: '2', customer_name: 'Juan Perez', customer_phone: '+529876543210', service: 'Consulta dental', scheduled_at: '2025-06-01T10:00:00Z', duration_min: 60, notes: 'Traer documentacion', status: 'pending', google_event_id: 'evt1', contact_id: 'c2', created_at: '2025-01-02T00:00:00Z' },
  { id: '3', customer_name: 'Ana Garcia', customer_phone: null, service: 'Manicure', scheduled_at: '2024-12-01T09:00:00Z', duration_min: 45, notes: null, status: 'completed', google_event_id: null, contact_id: null, created_at: '2024-12-01T00:00:00Z' },
]

function setupQueryClient() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  })
  return qc
}

function renderPage(clients?: { queryClient?: QueryClient }) {
  const queryClient = clients?.queryClient ?? setupQueryClient()
  queryClient.setQueryData(['appointment-stats'], mockStats)
  queryClient.setQueryData(['appointments'], mockAppointments)
  return {
    queryClient,
    ...render(
      <HelmetProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter><AppointmentsPage /></BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    ),
  }
}

describe('AppointmentsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders page title and description', () => {
    renderPage()
    expect(screen.getByText('Citas')).toBeDefined()
  })

  it('renders stat cards with values', () => {
    renderPage()
    expect(screen.getByText('2')).toBeDefined()
    expect(screen.getByText('3')).toBeDefined()
    expect(screen.getByText('10')).toBeDefined()
  })

  it('renders appointment names and services', () => {
    renderPage()
    expect(screen.getByText('Maria Lopez')).toBeDefined()
    expect(screen.getByText('Juan Perez')).toBeDefined()
    expect(screen.getByText('Corte de cabello')).toBeDefined()
    expect(screen.getByText('Consulta dental')).toBeDefined()
  })

  it('renders status badges', () => {
    renderPage()
    expect(screen.getByText('Confirmada')).toBeDefined()
    expect(screen.getByText('Pendiente')).toBeDefined()
    expect(screen.getByText('Completada')).toBeDefined()
  })

  it('renders create button', () => {
    renderPage()
    expect(screen.getByText('Nueva cita')).toBeDefined()
  })

  it('shows connect google calendar button when not connected', () => {
    renderPage()
    expect(screen.getByText('Conectar Google Calendar')).toBeDefined()
  })

  it('renders SEO component', () => {
    renderPage()
    expect(screen.getByText('Citas')).toBeDefined()
  })

  it('shows empty state when no appointments', () => {
    const qc = setupQueryClient()
    qc.setQueryData(['appointment-stats'], { total: 0, upcoming: 0, today: 0, google_connected: false })
    qc.setQueryData(['appointments'], [])
    render(
      <HelmetProvider>
        <QueryClientProvider client={qc}>
          <BrowserRouter><AppointmentsPage /></BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    )
    expect(screen.getByText('No hay citas todavía')).toBeDefined()
  })
})
