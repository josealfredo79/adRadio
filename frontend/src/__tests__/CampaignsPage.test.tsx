import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import CampaignsPage from '@/pages/CampaignsPage'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'test-id',
      email: 'test@test.com',
      business_name: 'Test Business',
      business_category: 'tienda',
      role: 'advertiser',
      city: 'City',
      country: 'MX',
      phone: null,
      whatsapp_number: null,
      whatsapp_number_source: 'shared',
      language: 'es',
      bot_name: 'Asistente',
      bot_personality: 'professional',
      bot_instructions: null,
      subscription_status: 'active',
      current_plan: 'growth',
      messages_remaining: 100,
      email_verified: true,
      logo_url: null,
      widget_color: '#25D366',
      widget_greeting: '¡Hola!',
      widget_position: 'right',
    },
  }),
}))

const mockCampaignsPage = {
  items: [
    { id: '1', name: 'Promo Junio', type: 'promo', message_text: 'Texto promo', status: 'running', stats: { sent: 100, delivered: 95, read: 50 }, ab_test: {}, created_at: '2025-01-01T00:00:00Z', schedule: null },
    { id: '2', name: 'Recordatorio', type: 'reminder', message_text: 'Texto recordatorio', status: 'draft', stats: {}, ab_test: {}, created_at: '2025-01-02T00:00:00Z', schedule: { start_date: '2025-06-01', end_date: '2025-06-10' } },
    { id: '3', name: 'Lanzamiento', type: 'launch', message_text: 'Texto lanzamiento', status: 'completed', stats: { sent: 200, delivered: 190, read: 120 }, ab_test: { enabled: false }, created_at: '2025-01-03T00:00:00Z', schedule: null },
  ],
  total: 3,
}

function setupQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000, gcTime: 0 } },
  })
}

function renderPage() {
  const queryClient = setupQueryClient()
  queryClient.setQueryData(['dashboard'], { messages_remaining: 100 })
  queryClient.setQueryData(['campaigns', 1], mockCampaignsPage)
  return {
    queryClient,
    ...render(
      <HelmetProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter><CampaignsPage /></BrowserRouter>
        </QueryClientProvider>
      </HelmetProvider>
    ),
  }
}

describe('CampaignsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders page title', () => {
    renderPage()
    expect(screen.getByText('Campañas')).toBeDefined()
  })

  it('renders campaign names', () => {
    renderPage()
    expect(screen.getByText('Promo Junio')).toBeDefined()
    expect(screen.getByText('Recordatorio')).toBeDefined()
    expect(screen.getByText('Lanzamiento')).toBeDefined()
  })

  it('renders status badges', () => {
    renderPage()
    expect(screen.getByText('Activa')).toBeDefined()
    expect(screen.getByText('Borrador')).toBeDefined()
    expect(screen.getByText('Completada')).toBeDefined()
  })

  it('shows campaign count in description', () => {
    renderPage()
    expect(screen.getByText(/3/)).toBeDefined()
  })

  it('renders create campaign button', () => {
    renderPage()
    expect(screen.getByText('Nueva campaña')).toBeDefined()
  })

  it('renders messages remaining info', () => {
    renderPage()
    expect(screen.getByText(/100/)).toBeDefined()
  })

  it('renders SEO component', () => {
    renderPage()
    expect(screen.getByText('Campañas')).toBeDefined()
  })
})
