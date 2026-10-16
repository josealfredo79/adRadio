import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import PilotCard from '@/pages/admin/PilotCard'
import { isCold, lastSeen } from '@/pages/admin/pilotTime'
import api from '@/lib/api'

const NOW = new Date('2026-10-15T18:00:00Z').getTime()

describe('lastSeen / isCold', () => {
  it('dice hace cuánto entró y marca a quien lleva más de 7 días', () => {
    expect(lastSeen(null)).toBe('nunca')
    expect(lastSeen('2026-10-15T15:00:00Z', NOW)).toBe('hace 3 h')
    expect(lastSeen('2026-10-12T18:00:00Z', NOW)).toBe('hace 3 d')
    expect(isCold(null)).toBe(true)
    expect(isCold('2026-10-12T18:00:00Z', NOW)).toBe(false)
    expect(isCold('2026-10-01T18:00:00Z', NOW)).toBe(true)
  })
})

describe('PilotCard', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('muestra el embudo, las semanas y cada negocio', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        embudo: { registrados: 7, verificaron_correo: 5, en_prueba: 4, pagando: 1, abrieron_pago_sin_pagar: 2,
          cancelaron: 0, prueba_a_pago_pct: 20 },
        semanas: [{ semana: '2026-10-12', registros: 3, verificaron: 2 }],
        negocios: [{ id: '1', negocio: 'CityCell', email: 'c@x.com', verificado: true, estado: 'trial', plan: 'trial',
          alta: '2026-10-01T00:00:00Z', ultimo_acceso: null, prueba_vence: '2026-10-20T00:00:00Z',
          chats_30d: 12, citas_30d: 3, pedidos_30d: 1, campanas_30d: 2, contactos: 40 }],
      },
    })
    render(<QueryClientProvider client={new QueryClient()}><PilotCard /></QueryClientProvider>)
    expect(await screen.findByText('CityCell')).toBeDefined()
    expect(screen.getByText('20%')).toBeDefined()
    expect(screen.getByText('3 (2 verif.)')).toBeDefined()
    expect(screen.getByText('nunca')).toBeDefined()
    expect(screen.getByText('Prueba')).toBeDefined()
  })
})
