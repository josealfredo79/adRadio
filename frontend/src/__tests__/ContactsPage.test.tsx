import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ToastProvider } from '@/contexts/ToastContext'
import ContactsPage from '@/pages/ContactsPage'

const mockContactsPage = {
  items: [
    { id: '1', name: 'Maria Lopez', phone: '+521234567890', email: 'maria@test.com', tags: ['vip', 'nuevo'], status: 'active', engagement_score: 85, created_at: '2025-01-01T00:00:00Z', city: 'CDMX' },
    { id: '2', name: 'Juan Perez', phone: '+529876543210', email: 'juan@test.com', tags: ['regular'], status: 'inactive', engagement_score: 30, created_at: '2025-01-02T00:00:00Z', city: 'Guadalajara' },
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
  queryClient.setQueryData(['contacts', 1], mockContactsPage)
  return {
    queryClient,
    ...render(
      <HelmetProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter><ToastProvider><ContactsPage /></ToastProvider></BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    ),
  }
}

describe('ContactsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders page title', () => {
    renderPage()
    expect(screen.getByText('Contactos')).toBeDefined()
  })

  it('renders contact names and phones', () => {
    renderPage()
    expect(screen.getAllByText('Maria Lopez').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Juan Perez').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('+521234567890').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('+529876543210').length).toBeGreaterThanOrEqual(1)
  })

  it('renders tag badges', () => {
    renderPage()
    expect(screen.getAllByText('vip').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('nuevo').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('regular').length).toBeGreaterThanOrEqual(1)
  })

  it('renders add contact button', () => {
    renderPage()
    expect(screen.getByText('Agregar')).toBeDefined()
  })

  it('renders search input', () => {
    renderPage()
    const search = screen.getByPlaceholderText('Buscar por nombre o teléfono...')
    expect(search).toBeDefined()
  })

  it('renders import CSV button', () => {
    renderPage()
    expect(screen.getByText('Importar CSV')).toBeDefined()
  })

  it('renders SEO component', () => {
    renderPage()
    expect(screen.getByText('Contactos')).toBeDefined()
  })
})
