import { describe, expect, it } from 'vitest'
import { stockGiro } from '@/pages/publicSite/utils'

// Fotos de portada cuando el dueño no sube las suyas: la carpeta "tienda" son
// fotos de ROPA, así que solo le tocan a ropa/boutique (visto 2026-10-08: una
// "Tienda de celulares" salió con fotos de ropa).
describe('stockGiro', () => {
  it('phone stores get phone-shop photos; electronics get technology', () => {
    expect(stockGiro('Tienda de celulares')).toBe('celulares')
    expect(stockGiro('Reparación de teléfonos')).toBe('celulares')
    expect(stockGiro('Electrónica')).toBe('tecnologia')
  })

  it('only clothing gets the clothing photos', () => {
    expect(stockGiro('Tienda de ropa')).toBe('tienda')
    expect(stockGiro('Boutique')).toBe('tienda')
  })

  it('any other store gets general shop photos', () => {
    expect(stockGiro('Tienda')).toBe('otro')
    expect(stockGiro('tienda')).toBe('otro')
    expect(stockGiro('Tienda de abarrotes')).toBe('otro')
  })

  it('keeps the existing trades', () => {
    expect(stockGiro('Taquería')).toBe('restaurante')
    expect(stockGiro('restaurante')).toBe('restaurante')
    expect(stockGiro('Estética')).toBe('belleza')
  })
})
