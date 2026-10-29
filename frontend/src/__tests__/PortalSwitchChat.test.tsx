import { fireEvent, render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { useState } from 'react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PortalPage from '@/pages/PortalPage'

// En computadora, /mi tiene la lista de chats a la izquierda: al pasar de un
// negocio a otro, el chat debe empezar de cero y no quedarse con la plática
// del negocio anterior (pasó con IaRadio → CityCell, 2026-10-29).

const NAMES: Record<string, string> = { tokA: 'IaRadio', tokB: 'CityCell' }

const portalData = (token: string) => ({
  push: { available: false, public_key: '', subscribed_devices: 0 },
  promotions: [],
  business: { advertiser_id: token, name: NAMES[token], agent: 'Asistente', color: '#7c3aed', greeting: '', site_theme: 'medianoche', slug: '', city: '', logo_url: '', whatsapp_number: '', quick_asks: [] },
  customer: { first_name: 'Alfredo' },
  account_available: false,
  upcoming_appointments: [],
})

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string) => Promise.resolve({ data: portalData(url.split('/')[3]) }),
    post: () => Promise.resolve({ data: {} }),
  },
}))
vi.mock('@/lib/useIsDesktop', () => ({ useIsDesktop: () => true }))
vi.mock('@/lib/useNativeViewport', () => ({ useNativeViewport: () => {} }))
vi.mock('@/components/SEO', () => ({ default: () => null }))
vi.mock('@/components/CustomerDesktopShell', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div>
      <Link to="/c/tokB">CityCell</Link>
      {children}
    </div>
  ),
}))
// El chat de verdad guarda su plática en su propio estado; este guarda con qué
// negocio se abrió, que es lo que se quedaba pegado.
function FakeChat({ portalToken }: { portalToken: string }) {
  const [openedWith] = useState(portalToken)
  return <p>plática de {NAMES[openedWith]}</p>
}
vi.mock('@/components/AgentChat', () => ({ default: FakeChat }))

describe('Cambiar de chat en /mi', () => {
  it('starts the new business chat fresh instead of keeping the old one', async () => {
    // Los dos chats ya se habían abierto: sin pantalla de "cargando" de por medio.
    const client = new QueryClient()
    client.setQueryData(['portal', 'tokA'], portalData('tokA'))
    client.setQueryData(['portal', 'tokB'], portalData('tokB'))
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/c/tokA']}>
          <Routes>
            <Route path="/c/:token" element={<PortalPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByText('plática de IaRadio')).toBeDefined()
    fireEvent.click(screen.getByRole('link', { name: 'CityCell' }))
    expect(await screen.findByText('plática de CityCell')).toBeDefined()
    expect(screen.queryByText('plática de IaRadio')).toBeNull()
  })
})
