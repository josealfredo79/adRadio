// Borrador del alta en el chat (OnboardingFlow / OnboardingCard): mismo
// formato que el perfil de backend/app/services/voice_setup.py.

export interface Draft {
  business_name: string | null
  business_category: string | null
  city: string | null
  address: string | null
  business_hours: Record<string, [string, string] | null> | null
  services: { name: string; price: number | null; description: string | null }[]
  [key: string]: unknown
}

export const EMPTY_DRAFT: Draft = {
  business_name: null, business_category: null, city: null, address: null, business_hours: null, services: [],
}

const GIROS: { re: RegExp; emoji: string; color: string; items: string[] }[] = [
  { re: /comid|taco|restaur|caf[eé]|pan|cocina|antoj|pizza|mariscos|torta|pollo/i, emoji: '🌮', color: '#e8590c', items: ['🌮', '🧀', '🥤'] },
  { re: /belle|est[eé]tic|sal[oó]n|barb|u[ñn]as|spa|maquill/i, emoji: '💇', color: '#d6336c', items: ['💇', '💅', '✨'] },
  { re: /salud|dent|m[eé]dic|consult|cl[ií]nic|psic|nutri|fisio|veterin/i, emoji: '🩺', color: '#1c7ed6', items: ['🩺', '💊', '📋'] },
  { re: /inmob|bienes ra|casa|depart|renta/i, emoji: '🏠', color: '#2f9e44', items: ['🏠', '🏢', '🔑'] },
]
const DEFAULT_GIRO = { emoji: '🛍️', color: '#7048e8', items: ['🛍️', '🎁', '📦'] }

export function giroLook(category: string | null) {
  return GIROS.find((g) => category && g.re.test(category)) ?? DEFAULT_GIRO
}

const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const
const SHORT: Record<string, string> = { mon: 'Lun', tue: 'Mar', wed: 'Mié', thu: 'Jue', fri: 'Vie', sat: 'Sáb', sun: 'Dom' }

/** "Lun–Vie · 9:00 – 18:00" agrupando días seguidos con el mismo horario. */
export function hoursLines(hours: Draft['business_hours']): string[] {
  if (!hours) return []
  const lines: string[] = []
  let i = 0
  while (i < DAYS.length) {
    const h = hours[DAYS[i]] ?? null
    let j = i
    while (j + 1 < DAYS.length && JSON.stringify(hours[DAYS[j + 1]] ?? null) === JSON.stringify(h)) j++
    const days = i === j ? SHORT[DAYS[i]] : `${SHORT[DAYS[i]]}–${SHORT[DAYS[j]]}`
    lines.push(`${days} · ${h ? `${h[0]} – ${h[1]}` : 'Cerrado'}`)
    i = j + 1
  }
  return lines
}

export function progressOf(d: Draft): number {
  const parts = [!!d.business_name, !!d.business_category, !!(d.city || d.address), !!d.business_hours, d.services.length > 0]
  return Math.round((parts.filter(Boolean).length / parts.length) * 100)
}
