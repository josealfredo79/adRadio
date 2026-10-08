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
  panader: '🥐', pastel: '🎂', cafe: '☕', café: '☕',
  barber: '💈', corte: '💈', uñas: '💅',
  farmacia: '💊', ferreter: '🔨', construc: '🏗️',
  corporativo: '💼', consultor: '💼', empresa: '💼', servicio: '💼',
  tecnolog: '💻', software: '💻',
}

export function categoryEmoji(category: string): string {
  const key = category.toLowerCase().trim()
  for (const [k, emoji] of Object.entries(CATEGORY_EMOJI)) {
    if (key.includes(k)) return emoji
  }
  return '🎙️'
}

/** El emoji del producto; si su categoría no dice nada ("Combos"), el del giro del negocio. */
export function productEmoji(productCategory: string, businessCategory: string): string {
  const own = categoryEmoji(productCategory || '')
  return own !== '🎙️' ? own : categoryEmoji(businessCategory || '')
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

// Fotos de stock (CC0, StockSnap) por giro para la portada mientras el dueño
// no suba las suyas. Viven en public/stock/{giro}/{n}.jpg.
const STOCK_COUNT: Record<string, number> = {
  restaurante: 5, tienda: 5, belleza: 5, gimnasio: 5, farmacia: 5, ferreteria: 5, panaderia: 5,
  corporativo: 5, inmobiliaria: 5, educacion: 5, automotriz: 5, tecnologia: 5, celulares: 5, otro: 5,
}
// En orden: lo específico antes que lo general ("Tienda de celulares" es
// tecnología, no la carpeta "tienda", que son fotos de ROPA).
const STOCK_KEYWORDS: [string, string][] = [
  ['celular', 'celulares'], ['teléfono', 'celulares'], ['telefon', 'celulares'], ['smartphone', 'celulares'],
  ['electrón', 'tecnologia'], ['electron', 'tecnologia'],
  ['cómputo', 'tecnologia'], ['computo', 'tecnologia'], ['computador', 'tecnologia'], ['laptop', 'tecnologia'], ['gadget', 'tecnologia'],
  // "abarrotes" contiene "bar": antes que restaurante.
  ['abarrot', 'otro'], ['miscel', 'otro'],
  ['restaur', 'restaurante'], ['comida', 'restaurante'], ['taquer', 'restaurante'], ['cocina', 'restaurante'], ['bar', 'restaurante'],
  ['panader', 'panaderia'], ['pastel', 'panaderia'], ['cafe', 'panaderia'], ['café', 'panaderia'],
  ['belleza', 'belleza'], ['estetic', 'belleza'], ['estétic', 'belleza'], ['salon', 'belleza'], ['salón', 'belleza'], ['barber', 'belleza'], ['spa', 'belleza'], ['uñas', 'belleza'],
  ['gimnasio', 'gimnasio'], ['fitness', 'gimnasio'], ['deporte', 'gimnasio'],
  ['farmacia', 'farmacia'], ['salud', 'farmacia'], ['clinic', 'farmacia'], ['clínic', 'farmacia'], ['dental', 'farmacia'], ['medic', 'farmacia'], ['médic', 'farmacia'],
  ['ferreter', 'ferreteria'], ['construc', 'ferreteria'],
  ['ropa', 'tienda'], ['boutique', 'tienda'], ['moda', 'tienda'], ['zapat', 'tienda'],
  // Cualquier otra tienda (abarrotes, papelería…): fotos de comercio en general.
  ['tienda', 'otro'], ['comercio', 'otro'],
  ['inmobil', 'inmobiliaria'], ['bienes', 'inmobiliaria'], ['terreno', 'inmobiliaria'], ['casa', 'inmobiliaria'],
  ['educa', 'educacion'], ['escuela', 'educacion'], ['academia', 'educacion'], ['curso', 'educacion'],
  ['automotr', 'automotriz'], ['taller', 'automotriz'], ['auto', 'automotriz'], ['mecánic', 'automotriz'], ['mecanic', 'automotriz'],
  ['tecnolog', 'tecnologia'], ['software', 'tecnologia'], ['commerce', 'tecnologia'],
  ['corporativo', 'corporativo'], ['consultor', 'corporativo'], ['servicio', 'corporativo'], ['empresa', 'corporativo'], ['abogad', 'corporativo'], ['legal', 'corporativo'],
]

export function stockGiro(category: string): string {
  const key = (category || '').toLowerCase().trim()
  // "tienda" a secas no es ropa (la carpeta "tienda" sí lo es).
  if (STOCK_COUNT[key] && key !== 'tienda') return key
  for (const [k, giro] of STOCK_KEYWORDS) if (key.includes(k)) return giro
  return 'otro'
}

export function stockPhotos(category: string): string[] {
  const giro = stockGiro(category)
  return Array.from({ length: STOCK_COUNT[giro] }, (_, i) => `/stock/${giro}/${i + 1}.jpg`)
}

const JS_DAYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']

/** "Abierto ahora · cierra 18:00", "Cerrado · abre mañana 9:00"… con la hora del visitante. */
export function openStatus(hours: BusinessHours | null | undefined, now = new Date()): { open: boolean; label: string } | null {
  if (!hours) return null
  const hhmm = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  const today = hours[JS_DAYS[now.getDay()]] ?? null
  if (today && hhmm >= today[0] && hhmm < today[1]) return { open: true, label: `Abierto ahora · cierra ${today[1]}` }
  if (today && hhmm < today[0]) return { open: false, label: `Cerrado · abre hoy ${today[0]}` }
  for (let d = 1; d <= 7; d++) {
    const next = hours[JS_DAYS[(now.getDay() + d) % 7]] ?? null
    if (next) return { open: false, label: `Cerrado · abre ${d === 1 ? 'mañana' : DAY_LABELS[JS_DAYS[(now.getDay() + d) % 7]].toLowerCase()} ${next[0]}` }
  }
  return null
}
