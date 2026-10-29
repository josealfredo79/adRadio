import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ModeSelector } from '@/pages/campaigns/components/ModeSelector'
import { quotaBadge } from '@/pages/campaigns/campaignQuota'
import { CampaignListHeader } from '@/pages/campaigns/components/CampaignListHeader'

// Campañas Fase A (docs/specs/2026-10-28-campanas-fase-a.md), casos 7 y 8.

const get = vi.fn()
vi.mock('@/lib/api', () => ({ default: { get: (...a: unknown[]) => get(...a) } }))
vi.mock('@/components/PrintButton', () => ({ default: () => null }))

function renderSelector() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <ModeSelector currentMode="regular" onModeChange={vi.fn()} />
    </QueryClientProvider>,
  )
}

describe('Campañas Fase A', () => {
  beforeEach(() => vi.clearAllMocks())

  it('caso 7: Arranque sees "1 de prueba este mes" on audio and image, not "tu plan no incluye"', async () => {
    get.mockResolvedValue({ data: { audio: { limit: 1, used: 0, trial: true }, image: { limit: 1, used: 0, trial: true } } })
    renderSelector()
    // 7 estilos de audio + el banner
    expect(await screen.findAllByText('1 de prueba este mes')).toHaveLength(8)
    expect(screen.queryByText(/no incluye/)).toBeNull()
  })

  it('caso 7: once the trial is used it shows the lock with the plan', () => {
    expect(quotaBadge({ limit: 1, used: 1, trial: true })).toBe('🔒 Desde el plan Negocio')
    expect(quotaBadge({ limit: 4, used: 3, trial: false })).toBe('Te queda 1 este mes')
    expect(quotaBadge({ limit: 4, used: 4, trial: false })).toBe('Ya usaste las de este mes')
    expect(quotaBadge({ limit: -1, used: 9, trial: false })).toBeNull()
  })

  it('caso 8: Secuencia, Saga and "Parrilla Semanal" are hidden', async () => {
    get.mockResolvedValue({ data: { audio: { limit: -1, used: 0, trial: false }, image: { limit: -1, used: 0, trial: false } } })
    renderSelector()
    expect(screen.getByText('🎙️ Cuña clásica')).toBeDefined()
    expect(screen.queryByText('📻 Secuencia')).toBeNull()
    expect(screen.queryByText('🎭 Saga')).toBeNull()
    render(<CampaignListHeader totalCampaigns={2} hasCampaigns noCredits={false} onExportCsv={vi.fn()} onShowCreate={vi.fn()} />)
    expect(screen.queryByText(/Parrilla Semanal/)).toBeNull()
    expect(screen.getByText('Nueva campaña')).toBeDefined()
  })
})
