import type { LoyaltyConfig } from '@/contexts/AuthContext'

// Encendida por defecto (igual que loyalty_service.LOYALTY_DEFAULTS); sin
// premio no se les ofrece a los clientes, así que se le pide al dueño.
export const LOYALTY_DEFAULTS: LoyaltyConfig = { enabled: true, stamps_required: 8, reward: '' }
export const LOYALTY_ANCHOR = 'tarjeta-lealtad'

export function loyaltyNeedsReward(cfg: LoyaltyConfig | null | undefined): boolean {
  const c = { ...LOYALTY_DEFAULTS, ...(cfg ?? {}) }
  return c.enabled && !c.reward.trim()
}
