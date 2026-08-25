export const waDigits = (n: string) => n.replace(/\D/g, '')

export const formatPrice = (price: string | null) =>
  price === null ? 'Cotizar' : new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(Number(price))

const CATEGORY_EMOJI: Record<string, string> = {
  restaurante: '🍽️', comida: '🍽️', cocina: '🍽️',
  salud: '🩺', clinica: '🩺', clínica: '🩺', dental: '🦷', dentista: '🦷',
  belleza: '💇', salon: '💇', salón: '💇', spa: '💆', estetica: '💆', estética: '💆',
  ropa: '👗', moda: '👗', boutique: '👗',
  taller: '🔧', mecanico: '🔧', mecánico: '🔧', automotriz: '🚗',
  gimnasio: '🏋️', fitness: '🏋️',
  abogado: '⚖️', legal: '⚖️',
  inmobiliaria: '🏠', bienes: '🏠',
  educacion: '📚', educación: '📚', escuela: '📚', academia: '📚',
  tienda: '🛍️', comercio: '🛍️',
  hotel: '🏨', turismo: '🏨',
}

export function categoryEmoji(category: string): string {
  const key = category.toLowerCase().trim()
  for (const [k, emoji] of Object.entries(CATEGORY_EMOJI)) {
    if (key.includes(k)) return emoji
  }
  return '🎙️'
}

export type BusinessHours = Record<string, [string, string] | null>

export const DAY_LABELS: Record<string, string> = {
  mon: 'Lun', tue: 'Mar', wed: 'Mié', thu: 'Jue', fri: 'Vie', sat: 'Sáb', sun: 'Dom',
}
export const DAY_ORDER = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

// Mirrors backend/app/services/availability_service.py::DEFAULT_BUSINESS_HOURS —
// what the public site renders when the advertiser hasn't set custom hours.
export const DEFAULT_BUSINESS_HOURS: BusinessHours = {
  mon: ['09:00', '18:00'],
  tue: ['09:00', '18:00'],
  wed: ['09:00', '18:00'],
  thu: ['09:00', '18:00'],
  fri: ['09:00', '18:00'],
  sat: ['09:00', '14:00'],
  sun: null,
}

// Mirrors backend/app/services/landing_sections.py::LANDING_SECTION_IDS —
// kept in sync by hand (same pre-existing pattern as SITE_THEME_KEYS/SITE_THEMES).
export const LANDING_SECTION_IDS = ['beneficios', 'opiniones', 'catalogo', 'nosotros_horario'] as const
export type LandingSectionId = (typeof LANDING_SECTION_IDS)[number]
export const LANDING_SECTION_LABELS: Record<LandingSectionId, string> = {
  beneficios: 'Beneficios',
  opiniones: 'Opiniones de clientes',
  catalogo: 'Catálogo (incluye "Tendencia" automático)',
  nosotros_horario: 'Sobre nosotros y horario',
}
export const DEFAULT_LANDING_SECTIONS: LandingSectionId[] = ['beneficios', 'opiniones', 'catalogo', 'nosotros_horario']

/** Groups consecutive days sharing the same open/close range into one row,
 * e.g. {mon..fri: [9,18], sat: [9,14], sun: null} -> "Lun-Vie 9:00-18:00", "Sáb 9:00-14:00", "Dom Cerrado". */
export function formatBusinessHours(hours: BusinessHours | null | undefined): { label: string; range: string }[] {
  if (!hours) return []
  const rows: { label: string; range: string }[] = []
  let i = 0
  while (i < DAY_ORDER.length) {
    const day = DAY_ORDER[i]
    const value = hours[day] ?? null
    const key = value ? `${value[0]}-${value[1]}` : 'closed'
    let j = i
    while (j + 1 < DAY_ORDER.length) {
      const nextValue = hours[DAY_ORDER[j + 1]] ?? null
      const nextKey = nextValue ? `${nextValue[0]}-${nextValue[1]}` : 'closed'
      if (nextKey !== key) break
      j++
    }
    const label = i === j ? DAY_LABELS[day] : `${DAY_LABELS[day]}-${DAY_LABELS[DAY_ORDER[j]]}`
    rows.push({ label, range: value ? `${value[0]} - ${value[1]}` : 'Cerrado' })
    i = j + 1
  }
  return rows
}
