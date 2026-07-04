import { describe, it, expect } from 'vitest'
import { cn, formatNumber, formatCurrency, formatDate } from '../utils'

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('px-4', 'py-2')).toBe('px-4 py-2')
  })

  it('handles conditional classes (falsy)', () => {
    const isHidden = false
    expect(cn('base', isHidden && 'hidden')).toBe('base')
  })

  it('resolves tailwind conflicts (last wins)', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4')
  })
})

describe('formatNumber', () => {
  it('formats with es-MX locale', () => {
    expect(formatNumber(1000)).toBe('1,000')
  })

  it('handles decimals', () => {
    expect(formatNumber(1234.56)).toBe('1,234.56')
  })
})

describe('formatCurrency', () => {
  it('formats in USD by default', () => {
    const result = formatCurrency(499)
    expect(result).toContain('499')
    expect(result).toContain('USD')
  })

  it('accepts custom currency', () => {
    const result = formatCurrency(999, 'MXN')
    expect(result).toContain('999')
    expect(result).toMatch(/[$MXN]/)
  })
})

describe('formatDate', () => {
  it('formats date string', () => {
    const result = formatDate('2024-01-15T10:30:00')
    expect(result).toContain('2024')
    expect(result).toContain('10')
  })

  it('handles Date object', () => {
    const result = formatDate(new Date('2024-06-01T14:00:00'))
    expect(result).toContain('2024')
  })
})
