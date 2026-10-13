import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import WhatsappWizard from '@/components/WhatsappWizard'

// docs/specs/2026-10-12-conectar-con-meta.md — lo que ve el negocio.
vi.mock('@/lib/api', () => ({ default: { get: vi.fn(() => new Promise(() => {})), post: vi.fn() } }))

function renderWizard(enabled: boolean) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  qc.setQueryData(['whatsapp-connection'], { status: 'not_connected' })
  qc.setQueryData(['whatsapp-embedded-config'], { app_id: '1', config_id: 'c', enabled })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <WhatsappWizard />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('WhatsappWizard — Conectar con Meta', () => {
  it('casos 1 y 2: hidden when the server says it is not enabled for this user', () => {
    renderWizard(false)
    expect(screen.queryByText('Conectar con Meta')).toBeNull()
  })

  it('caso 5: shows the button with the Meta billing and new-number notices', () => {
    renderWizard(true)
    expect(screen.getByText('Conectar con Meta')).toBeDefined()
    expect(screen.getByText(/Meta puede pedirte una tarjeta/)).toBeDefined()
    expect(screen.getByText(/Contestar a tus clientes es gratis/)).toBeDefined()
    expect(screen.getByText(/esté en la app de WhatsApp de un celular/)).toBeDefined()
  })
})
