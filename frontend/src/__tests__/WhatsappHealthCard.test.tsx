import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect } from 'vitest'
import WhatsappHealthCard from '@/components/WhatsappHealthCard'

function renderCard(connectionStatus: string, health?: Record<string, unknown>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  })
  queryClient.setQueryData(['whatsapp-connection'], { status: connectionStatus })
  if (health) queryClient.setQueryData(['whatsapp-health'], health)
  return render(
    <QueryClientProvider client={queryClient}>
      <WhatsappHealthCard />
    </QueryClientProvider>
  )
}

const baseHealth = {
  quality_rating: 'GREEN',
  messaging_tier: 'TIER_1K',
  tier_recipient_limit: 1000,
  send_throttle_per_hour: 60,
  warmup_active: false,
  warmup_recipient_cap: null,
  warmup_days_remaining: null,
  recipients_sent_last_24h: 40,
  effective_recipient_limit: 1000,
  active_campaigns_count: 2,
  paused_campaigns_count: 0,
  billing_error_recent: false,
  billing_error_last_seen: null,
}

describe('WhatsappHealthCard', () => {
  it('renders nothing when WhatsApp is not connected', () => {
    const { container } = renderCard('not_connected', baseHealth)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing while health data has not loaded yet', () => {
    const { container } = renderCard('connected')
    expect(container.firstChild).toBeNull()
  })

  it('shows the quality rating and tier for a healthy connected account', () => {
    renderCard('connected', baseHealth)
    expect(screen.getByText('Salud de la cuenta de WhatsApp')).toBeDefined()
    expect(screen.getByText('Buena')).toBeDefined()
    expect(screen.getByText(/TIER_1K/)).toBeDefined()
    expect(screen.queryByText(/campaña.*pausada/)).toBeNull()
  })

  it('shows a warmup banner with days remaining for a new number', () => {
    renderCard('connected', {
      ...baseHealth,
      quality_rating: null,
      messaging_tier: null,
      warmup_active: true,
      warmup_recipient_cap: 20,
      warmup_days_remaining: 28.5,
      effective_recipient_limit: 20,
    })
    expect(screen.getByText(/calentamiento/)).toBeDefined()
    expect(screen.getByText(/20 destinatarios nuevos\/24h/)).toBeDefined()
    expect(screen.getByText(/Faltan ~29 días/)).toBeDefined()
  })

  it('warns about paused campaigns when there are any', () => {
    renderCard('connected', { ...baseHealth, paused_campaigns_count: 2 })
    expect(screen.getByText(/Tienes 2 campañas pausadas/)).toBeDefined()
  })

  it('uses singular phrasing for exactly one paused campaign', () => {
    renderCard('connected', { ...baseHealth, paused_campaigns_count: 1 })
    expect(screen.getByText(/Tienes 1 campaña pausada — /)).toBeDefined()
  })

  it('warns about a missing WhatsApp payment method when 131042 was seen recently', () => {
    renderCard('connected', {
      ...baseHealth,
      billing_error_recent: true,
      billing_error_last_seen: '2026-08-29T12:00:00Z',
    })
    expect(screen.getByText(/método de pago/)).toBeDefined()
    expect(screen.getByText(/131042/)).toBeDefined()
  })

  it('shows a critical-rating warning when quality is RED', () => {
    renderCard('connected', { ...baseHealth, quality_rating: 'RED' })
    expect(screen.getByText(/calidad crítica/)).toBeDefined()
    expect(screen.getByText(/se pausaron automáticamente/)).toBeDefined()
  })

  it('renders "sin tope" when there is no effective recipient limit', () => {
    renderCard('connected', { ...baseHealth, effective_recipient_limit: null })
    expect(screen.getByText(/sin tope/)).toBeDefined()
  })
})
