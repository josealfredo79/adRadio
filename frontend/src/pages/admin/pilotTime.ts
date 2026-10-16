// Último acceso de cada negocio en el panel del piloto (PilotCard.tsx).

/** "hace 3 h", "hace 2 d", "nunca". */
export function lastSeen(iso: string | null, now = Date.now()): string {
  if (!iso) return 'nunca'
  const hours = Math.floor((now - new Date(iso).getTime()) / 3_600_000)
  if (hours < 1) return 'hace menos de 1 h'
  if (hours < 24) return `hace ${hours} h`
  return `hace ${Math.floor(hours / 24)} d`
}

/** Sin entrar en 7 días (o nunca): el negocio se está enfriando. */
export function isCold(iso: string | null, now = Date.now()): boolean {
  return !iso || now - new Date(iso).getTime() > 7 * 86_400_000
}
