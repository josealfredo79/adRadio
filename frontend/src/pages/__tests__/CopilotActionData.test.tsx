import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ActionData } from '../CopilotPage'

// Caso real (14-oct): "¿cuántos contactos tengo?" pintaba cada contacto como JSON crudo.
describe('ActionData del Copiloto', () => {
  it('muestra cada contacto en una línea legible, sin ids ni JSON', () => {
    const { container } = render(
      <ActionData
        data={{
          count: 2,
          items: [
            { id: '2263f1b1', name: 'Tú (prueba)', phone: '+529531953182', tags: ['prueba'], status: 'active', pipeline_stage: 'nuevo' },
            { id: 'a192ced1', name: 'Movimiento', phone: '+529515199084', tags: [], status: 'active', pipeline_stage: 'nuevo' },
          ],
        }}
      />,
    )
    expect(screen.getByText('Total')).toBeTruthy()
    expect(screen.getByText('Tú (prueba) · +529531953182 · prueba · activo · nuevo')).toBeTruthy()
    expect(screen.getByText('Movimiento · +529515199084 · activo · nuevo')).toBeTruthy()
    expect(container.textContent).not.toContain('{')
    expect(container.textContent).not.toContain('2263f1b1')
  })
})

describe('ActionData — resumen de analíticas', () => {
  it('lo muestra en español y con % en los porcentajes', () => {
    render(
      <ActionData
        data={{
          totals: { messages_outbound: 179, replied: 4 },
          rates: { response_rate: 66.7 },
          business: { active_contacts: 6 },
        }}
      />,
    )
    expect(screen.getByText('Mensajes enviados')).toBeDefined()
    expect(screen.getByText('Clientes que respondieron')).toBeDefined()
    expect(screen.getByText('Contactos activos')).toBeDefined()
    expect(screen.getByText('66.7%')).toBeDefined()
    expect(screen.queryByText(/Messages Outbound|Response Rate/)).toBeNull()
  })
})

// Caso real (19-oct): la tarjeta del cobro salía con "Saved", "Today Total"… y montos sin $.
describe('ActionData — cobro', () => {
  it('lo muestra en español y con $', () => {
    render(
      <ActionData
        data={{
          saved: true,
          amount: 85,
          customer: { name: 'Cliente Prueba', phone_last4: '4567' },
          stamped: false,
          today_total: 1250.5,
          today_count: 1,
        }}
      />,
    )
    expect(screen.getByText('Monto')).toBeDefined()
    expect(screen.getByText('$85')).toBeDefined()
    expect(screen.getByText('Llevas hoy')).toBeDefined()
    expect(screen.getByText('$1,250.50')).toBeDefined()
    expect(screen.getByText('Ventas hoy')).toBeDefined()
    expect(screen.queryByText(/Saved|Amount|Today Total|Phone Last4|Stamped/)).toBeNull()
  })
})
