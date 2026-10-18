import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, it, expect, vi } from 'vitest'
import api from '@/lib/api'
import WhatsappWizard from '@/components/WhatsappWizard'

// docs/specs/2026-10-12-conectar-con-meta.md y 2026-10-17-meta-sin-friccion.md — lo que ve el negocio.
vi.mock('@/lib/api', () => ({
  default: { get: vi.fn(() => new Promise(() => {})), post: vi.fn(() => Promise.resolve({ data: { ok: true } })) },
  getApiError: (_e: unknown, fallback: string) => fallback,
}))
const auth = vi.hoisted(() => ({ role: 'advertiser' }))
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: { role: auth.role } }) }))

function renderWizard(enabled: boolean, status = 'not_connected') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  qc.setQueryData(['whatsapp-connection'], { status })
  qc.setQueryData(['whatsapp-embedded-config'], {
    app_id: '1', config_id: 'c', enabled, free_service_messages: 1000, service_price_mxn: 0.16,
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <WhatsappWizard />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  auth.role = 'advertiser'
  vi.mocked(api.post).mockClear()
})

describe('WhatsappWizard — Conectar con Meta', () => {
  it('casos 1 y 2: hidden when the server says it is not enabled for this user', () => {
    renderWizard(false)
    expect(screen.queryByText('Conectar con Meta')).toBeNull()
  })

  it('sin fricción caso 5: shows the button with what to have at hand and the real Meta pricing', () => {
    renderWizard(true)
    expect(screen.getByText('Conectar con Meta')).toBeDefined()
    expect(screen.getByText(/Antes de empezar ten a la mano/)).toBeDefined()
    expect(screen.getByText(/Tu cuenta de Facebook/)).toBeDefined()
    expect(screen.getByText(/Meta puede pedirte una tarjeta/)).toBeDefined()
    expect(screen.getByText(/primeras 1,000 respuestas/)).toBeDefined()
    expect(screen.getByText(/\$0\.16 por respuesta/)).toBeDefined()
    expect(screen.queryByText(/Contestar a tus clientes es gratis/)).toBeNull()
    expect(screen.getByText(/ninguna app de WhatsApp/)).toBeDefined()
  })

  it('coexistencia caso 11: explains using the same number and what stops working on the phone', () => {
    renderWizard(true)
    expect(screen.getByText(/Puedes usar tu número de siempre/)).toBeDefined()
    expect(screen.getByText(/dejan de funcionar en el celular: grupos, mensajes temporales/)).toBeDefined()
  })
})

describe('WhatsappWizard — Meta sin fricción', () => {
  it('caso 1: an owner without the button sees the bot already works and a help button, no manual guide', () => {
    renderWizard(false)
    expect(screen.getByText(/Tu bot ya atiende a tus clientes en/)).toBeDefined()
    expect(screen.getByText('Quiero conectar mi WhatsApp')).toBeDefined()
    expect(screen.queryByText(/Conectar a mano/)).toBeNull()
    expect(screen.queryByText(/Guía paso a paso/)).toBeNull()
    expect(screen.queryByPlaceholderText('EAAG...')).toBeNull()
  })

  it('caso 2: tapping help sends the request and confirms', async () => {
    renderWizard(false)
    fireEvent.click(screen.getByText('Quiero conectar mi WhatsApp'))
    await waitFor(() => expect(screen.getByText(/te escribimos pronto/)).toBeDefined())
    expect(api.post).toHaveBeenCalledWith('/me/whatsapp-connection/help')
  })

  it('caso 4: an admin keeps the manual connection, folded under "avanzado"', () => {
    auth.role = 'admin'
    renderWizard(true)
    expect(screen.getByText('Conectar con Meta')).toBeDefined()
    expect(screen.queryByText('Quiero conectar mi WhatsApp')).toBeNull()
    expect(screen.queryByText(/Guía paso a paso/)).toBeNull()
    fireEvent.click(screen.getByText(/Conectar a mano \(avanzado/))
    expect(screen.getByText(/Guía paso a paso/)).toBeDefined()
  })

  it('caso 5: an owner with the button does not see the help button nor the manual guide', () => {
    renderWizard(true)
    expect(screen.queryByText('Quiero conectar mi WhatsApp')).toBeNull()
    expect(screen.queryByText(/Conectar a mano/)).toBeNull()
  })

  it('an owner already connected is not asked to connect', () => {
    renderWizard(false, 'connected')
    expect(screen.queryByText('Quiero conectar mi WhatsApp')).toBeNull()
    expect(screen.queryByText(/Tu bot ya atiende a tus clientes en/)).toBeNull()
  })
})
