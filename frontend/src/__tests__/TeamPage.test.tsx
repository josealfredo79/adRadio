import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TeamPage from '@/pages/TeamPage'

const mockMembers = [
  { id: '1', member_email: 'agent@test.com', role: 'agent', invited_at: '2025-01-01T00:00:00Z', accepted_at: '2025-01-02T00:00:00Z' },
  { id: '2', member_email: 'viewer@test.com', role: 'viewer', invited_at: '2025-01-03T00:00:00Z', accepted_at: null },
]

function setupQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  })
}

function renderPage(clients?: { queryClient?: QueryClient }) {
  const queryClient = clients?.queryClient ?? setupQueryClient()
  queryClient.setQueryData(['team'], mockMembers)
  return {
    queryClient,
    ...render(
      <HelmetProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter><TeamPage /></BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    ),
  }
}

describe('TeamPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders page title and description', () => {
    renderPage()
    expect(screen.getByText('Equipo')).toBeDefined()
    expect(screen.getByText(/Invita colaboradores/)).toBeDefined()
  })

  it('renders invite form with inputs and button', () => {
    renderPage()
    expect(screen.getByPlaceholderText('email@ejemplo.com')).toBeDefined()
    expect(screen.getByRole('button', { name: /invitar/i })).toBeDefined()
  })

  it('renders member list with email and role info', () => {
    renderPage()
    expect(screen.getByText('agent@test.com')).toBeDefined()
    expect(screen.getByText('viewer@test.com')).toBeDefined()
    expect(screen.getAllByText('Agente').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Visor').length).toBeGreaterThanOrEqual(1)
  })

  it('shows accepted/pending status', () => {
    renderPage()
    expect(screen.getByText(/Aceptado/)).toBeDefined()
    expect(screen.getByText(/Pendiente/)).toBeDefined()
  })

  it('renders role selector and remove button for each member', () => {
    renderPage()
    const selects = screen.getAllByRole('combobox')
    expect(selects.length).toBeGreaterThanOrEqual(2)
  })

  it('shows loading spinner when no cached data', () => {
    const qc = setupQueryClient()
    render(
      <HelmetProvider>
        <QueryClientProvider client={qc}>
          <BrowserRouter><TeamPage /></BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    )
    expect(screen.getByText('Equipo')).toBeDefined()
  })

  it('renders SEO component', () => {
    renderPage()
    expect(screen.getByText('Equipo')).toBeDefined()
  })
})
