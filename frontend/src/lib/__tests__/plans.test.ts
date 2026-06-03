import { describe, it, expect } from 'vitest'
import { PLANS_CONFIG, PLANS_MAP, LANDING_PLANS } from '../plans'

describe('PLANS_CONFIG', () => {
  it('has 5 plans', () => {
    expect(PLANS_CONFIG).toHaveLength(5)
  })

  it('every plan has required fields', () => {
    for (const plan of PLANS_CONFIG) {
      expect(plan.key).toBeTruthy()
      expect(plan.name).toBeTruthy()
      expect(typeof plan.price_mxn).toBe('number')
      expect(typeof plan.messages).toBe('number')
      expect(Array.isArray(plan.features)).toBe(true)
      expect(plan.features.length).toBeGreaterThan(0)
    }
  })

  it('growth is marked popular', () => {
    const growth = PLANS_CONFIG.find((p) => p.key === 'growth')
    expect(growth?.popular).toBe(true)
  })

  it('starter has lowest price', () => {
    const prices = PLANS_CONFIG.map((p) => p.price_mxn)
    expect(Math.min(...prices)).toBe(499)
  })

  it('enterprise has highest price', () => {
    const prices = PLANS_CONFIG.map((p) => p.price_mxn)
    expect(Math.max(...prices)).toBe(19999)
  })
})

describe('PLANS_MAP', () => {
  it('maps all keys', () => {
    expect(Object.keys(PLANS_MAP)).toEqual(
      expect.arrayContaining(['starter', 'growth', 'pro', 'business', 'enterprise']),
    )
  })

  it('returns correct plan by key', () => {
    expect(PLANS_MAP.starter.name).toBe('Starter')
    expect(PLANS_MAP.enterprise.messages).toBe(10000)
  })
})

describe('LANDING_PLANS', () => {
  it('excludes enterprise', () => {
    const keys = LANDING_PLANS.map((p) => p.key)
    expect(keys).not.toContain('enterprise')
    expect(keys).toHaveLength(4)
  })
})
