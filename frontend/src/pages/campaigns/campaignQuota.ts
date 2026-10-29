// Cuántos audios e imágenes le quedan al negocio este mes (GET /campaigns/quota;
// Arranque: 1 de prueba de cada uno, spec 2026-10-28-campanas-fase-a).

export interface QuotaKind { limit: number; used: number; trial: boolean }
export interface CampaignQuota { audio: QuotaKind; image: QuotaKind }

/** "1 de prueba este mes", "🔒 Desde Negocio" o "Te quedan 3 este mes"; null sin tope. */
export function quotaBadge(q: QuotaKind | undefined): string | null {
  if (!q || q.limit < 0) return null
  const left = Math.max(0, q.limit - q.used)
  if (q.trial) return left > 0 ? `${left} de prueba este mes` : '🔒 Desde el plan Negocio'
  return left > 0 ? `Te ${left === 1 ? 'queda 1' : `quedan ${left}`} este mes` : 'Ya usaste las de este mes'
}
