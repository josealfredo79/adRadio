import { describe, it, expect } from 'vitest'
import { ADDONS_CONFIG, LANDING_PLANS, PLANS_CONFIG, PLANS_MAP, planDisplayName } from '../plans'

// Debe coincidir con backend/app/core/plans.py (rediseño 2026-10-01).
describe('PLANS_CONFIG', () => {
  it('has the 4 current plans with their new names', () => {
    expect(PLANS_CONFIG.map((p) => [p.key, p.name])).toEqual([
      ['starter', 'Arranque'],
      ['growth', 'Negocio'],
      ['pro', 'Crecimiento'],
      ['enterprise', 'Empresa'],
    ])
  })

  it('every plan has required fields', () => {
    for (const plan of PLANS_CONFIG) {
      expect(plan.key).toBeTruthy()
      expect(typeof plan.price_mxn).toBe('number')
      expect(typeof plan.messages).toBe('number')
      expect(typeof plan.conversations).toBe('number')
      expect(plan.features.length).toBeGreaterThan(0)
    }
  })

  it('prices and quotas match the backend', () => {
    expect(PLANS_CONFIG.map((p) => p.price_mxn)).toEqual([449, 899, 1799, 4999])
    expect(PLANS_CONFIG.map((p) => p.conversations)).toEqual([300, 1000, 3000, -1])
    expect(PLANS_CONFIG.map((p) => p.messages)).toEqual([150, 500, 1500, 5000])
  })

  it('Negocio is the popular one and Empresa is quoted', () => {
    expect(PLANS_MAP.growth.popular).toBe(true)
    expect(PLANS_MAP.enterprise.custom).toBe(true)
  })

  it('has no fake reference prices', () => {
    for (const plan of PLANS_CONFIG) {
      expect(plan).not.toHaveProperty('referencePriceMxn')
    }
  })
})

describe('LANDING_PLANS', () => {
  it('shows the 3 self-serve plans', () => {
    expect(LANDING_PLANS.map((p) => p.key)).toEqual(['starter', 'growth', 'pro'])
  })
})

describe('planDisplayName', () => {
  it('names current, retired and trial plans', () => {
    expect(planDisplayName('growth')).toBe('Negocio')
    expect(planDisplayName('trial')).toBe('Prueba gratis')
    expect(planDisplayName(undefined)).toBe('Prueba gratis')
    expect(planDisplayName('micro')).toContain('Micro')
  })
})

describe('ADDONS_CONFIG', () => {
  it('matches backend add-ons', () => {
    expect(ADDONS_CONFIG.map((a) => [a.key, a.price_mxn])).toEqual([
      ['conversations_500', 149],
      ['messages_500', 99],
    ])
  })
})
