import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { SendCampaignModal } from '@/pages/campaigns/components/SendCampaignModal'
import type { Campaign } from '@/pages/campaigns/types'

// Campañas por web sin reglas de WhatsApp (docs/specs/2026-10-13-web-sin-reglas-whatsapp.md).

const get = vi.fn()
vi.mock('@/lib/api', () => ({ default: { get: (...a: unknown[]) => get(...a) } }))

const CAMPAIGN = { id: 'c1', name: 'Promo Micas' } as Campaign

function renderModal(reach: Record<string, unknown>) {
  get.mockResolvedValue({ data: { total: 0, web: 0, whatsapp: 0, whatsapp_cost_mxn: 0, web_supported: true, ...reach } })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <SendCampaignModal campaign={CAMPAIGN} sending={false} onSend={() => {}} onClose={() => {}} />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('SendCampaignModal', () => {
  beforeEach(() => vi.clearAllMocks())

  it('says how many get it by web without a notification (already had one today)', async () => {
    renderModal({ total: 2, web: 1, web_silent: 1, whatsapp: 1, whatsapp_cost_mxn: 0.73 })
    expect(await screen.findByText(/sin sonar: ya tuvieron un aviso hoy/)).toBeDefined()
  })

  it('no silent note when everyone will get the notification', async () => {
    renderModal({ total: 2, web: 1, web_silent: 0, whatsapp: 1 })
    await screen.findByText(/Solo por web/)
    expect(screen.queryByText(/sin sonar/)).toBeNull()
  })

  it('offers only "Solo por web" when nobody gets it by WhatsApp', async () => {
    renderModal({ total: 1, web: 1, whatsapp: 0 })
    expect(await screen.findByText(/Solo por web — gratis \(1 cliente\)/)).toBeDefined()
    expect(screen.queryByText(/Enviar a todos/)).toBeNull()
  })

  it('offers both when some go by WhatsApp', async () => {
    renderModal({ total: 3, web: 1, whatsapp: 2, whatsapp_cost_mxn: 1.47 })
    expect(await screen.findByText(/Solo por web — gratis \(1 cliente\)/)).toBeDefined()
    expect(screen.getByText(/Enviar a todos \(3 clientes\)/)).toBeDefined()
  })

  it('without its own WhatsApp: no WhatsApp count or cost, says who misses it and links to connect the chip', async () => {
    renderModal({ total: 1, web: 1, whatsapp: 0, whatsapp_connected: false, whatsapp_unreachable: 4 })
    expect(await screen.findByText(/Solo por web — gratis \(1 cliente\)/)).toBeDefined()
    expect(screen.getByText(/no les llega por WhatsApp: tu WhatsApp no está conectado/)).toBeDefined()
    expect(screen.getByRole('link', { name: /Conecta el número de tu chip/ }).getAttribute('href')).toBe('/app/settings')
    expect(screen.queryByText(/por WhatsApp —/)).toBeNull()
    expect(screen.queryByText(/Enviar a todos/)).toBeNull()
  })

  it('caso 13: "Solo por web" also counts the ones without notifications (it stays in their chat)', async () => {
    renderModal({ total: 1, web: 0, web_chat: 3, whatsapp: 0, whatsapp_connected: false, whatsapp_unreachable: 3 })
    expect(await screen.findByText(/Solo por web — gratis \(3 clientes\)/)).toBeDefined()
    expect(screen.getByText(/a 3 clientes sin avisos les queda en su chat/)).toBeDefined()
  })

  it('with its own WhatsApp the cost goes to the business card, in whole pesos when exact', async () => {
    renderModal({ total: 16, web: 1, whatsapp: 15, whatsapp_cost_mxn: 11, whatsapp_connected: true })
    expect(await screen.findByText(/Meta le cobra a tu tarjeta hasta/)).toBeDefined()
    expect(screen.getByText('≈ $11')).toBeDefined()
  })
})
