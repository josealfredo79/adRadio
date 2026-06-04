import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import SettingsPage from '@/pages/SettingsPage'

vi.mock('@/contexts/AuthContext', () => {
  const u = { id: '1', email: 'admin@test.com', business_name: 'Mi Negocio', business_category: 'restaurante', city: 'CDMX', country: 'MX', phone: '+525511111111', whatsapp_number: '+525522222222', whatsapp_number_source: 'pool', language: 'es', bot_name: 'Sofia', bot_personality: 'friendly', current_plan: 'pro' }
  return { useAuth: () => ({ user: u, setUser: vi.fn(), loading: false }) }
})

function setupQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  })
}

function renderPage() {
  const queryClient = setupQueryClient()
  queryClient.setQueryData(['dashboard'], {
    plan: 'pro',
    subscription_status: 'active',
    messages_remaining: 500,
  })
  queryClient.setQueryData(['user-webhooks'], [])
  queryClient.setQueryData(['white-label'], null)
  queryClient.setQueryData(['api-keys'], [])
  return {
    queryClient,
    ...render(
      <HelmetProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter><SettingsPage /></BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    ),
  }
}

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders page title and description', () => {
    renderPage()
    expect(screen.getByText('Configuración')).toBeDefined()
    expect(screen.getByText(/Ajusta los datos/)).toBeDefined()
  })

  it('renders business info section', () => {
    renderPage()
    expect(screen.getByText('Datos del negocio')).toBeDefined()
    expect(screen.getByText('Nombre del negocio')).toBeDefined()
    expect(screen.getByText('Categoría')).toBeDefined()
  })

  it('renders bot config section', () => {
    renderPage()
    expect(screen.getByText('Configuración del bot')).toBeDefined()
    expect(screen.getByText('Nombre del bot')).toBeDefined()
    expect(screen.getByText('Personalidad')).toBeDefined()
  })

  it('renders subscription section', () => {
    renderPage()
    expect(screen.getByText('Suscripción')).toBeDefined()
    expect(screen.getByText('500')).toBeDefined()
  })

  it('renders change password section', () => {
    renderPage()
    expect(screen.getByText('Cambiar contraseña')).toBeDefined()
    expect(screen.getByPlaceholderText('••••••••')).toBeDefined()
    expect(screen.getByPlaceholderText('Mínimo 8 caracteres')).toBeDefined()
  })

  it('renders webhooks section', () => {
    renderPage()
    expect(screen.getByText('Webhooks')).toBeDefined()
  })

  it('renders white label section', () => {
    renderPage()
    expect(screen.getByText('White Label')).toBeDefined()
  })

  it('renders API keys section', () => {
    renderPage()
    expect(screen.getByText('API Keys')).toBeDefined()
  })

  it('renders music attribution', () => {
    renderPage()
    expect(screen.getByText(/Kevin MacLeod/)).toBeDefined()
  })

  it('renders SEO component', () => {
    renderPage()
    expect(screen.getByText('Configuración')).toBeDefined()
  })

  it('renders save button', () => {
    renderPage()
    const btns = screen.getAllByText('Guardar cambios')
    expect(btns.length).toBeGreaterThanOrEqual(1)
  })
})
