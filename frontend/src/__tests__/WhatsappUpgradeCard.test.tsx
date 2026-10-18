import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, it, expect, vi } from 'vitest'
import WhatsappUpgradeCard from '@/components/WhatsappUpgradeCard'
import FaqSection from '@/pages/landing/components/FaqSection'

// docs/specs/2026-10-17-meta-sin-friccion.md, casos 6, 7 y 8.
vi.mock('@/lib/api', () => ({ default: { get: vi.fn(() => new Promise(() => {})) } }))

function renderCard(webCustomers: number, status = 'not_connected') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  qc.setQueryData(['whatsapp-connection'], { status })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <WhatsappUpgradeCard webCustomers={webCustomers} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => localStorage.clear())

describe('WhatsappUpgradeCard', () => {
  it('caso 6: with 5+ web customers and no WhatsApp, offers connecting as an upgrade', () => {
    renderCard(7)
    expect(screen.getByText(/Ya atendiste 7 clientes por tu página/)).toBeDefined()
    expect(screen.getByText(/Conectar mi WhatsApp/).getAttribute('href')).toBe('/app/settings#whatsapp')
  })

  it('caso 6: it can be closed and stays closed', () => {
    const { unmount } = renderCard(7)
    fireEvent.click(screen.getByLabelText('Cerrar'))
    expect(screen.queryByText(/Ya atendiste/)).toBeNull()
    unmount()
    renderCard(7)
    expect(screen.queryByText(/Ya atendiste/)).toBeNull()
  })

  it('caso 7: hidden with fewer than 5 web customers', () => {
    renderCard(4)
    expect(screen.queryByText(/Ya atendiste/)).toBeNull()
  })

  it('caso 7: hidden when WhatsApp is already connected (incl. the central number account)', () => {
    renderCard(30, 'connected')
    expect(screen.queryByText(/Ya atendiste/)).toBeNull()
  })
})

describe('Landing FAQ', () => {
  it('caso 8: says you start without connecting anything', () => {
    const { container } = render(<FaqSection />)
    expect(container.textContent).toMatch(/Arrancas sin conectar nada/)
  })
})
