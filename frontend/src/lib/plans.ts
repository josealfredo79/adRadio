/**
 * plans.ts — Fuente de verdad del frontend para los planes de IaRadio.
 *
 * Debe coincidir con backend/app/core/plans.py (precios, cuotas, límites).
 * Rediseño 2026-10-01: 3 planes públicos + Empresa. Las claves internas
 * (starter/growth/pro/enterprise) no cambian — las usan la BD, Stripe y el
 * gating por plan —; cambian nombre, precio y lo que incluye.
 *
 * Sin precios "de referencia" tachados: eran descuentos que nunca existieron.
 */

export type PlanKey = 'starter' | 'growth' | 'pro' | 'enterprise'

export interface PlanDefinition {
  key: PlanKey
  name: string
  price_mxn: number
  price_usd: number
  /** Envíos de campaña por WhatsApp al mes (los que inicia el negocio) */
  messages: number
  /** Conversaciones del bot con IA al mes (WhatsApp + web); -1 = a medida */
  conversations: number
  days: number
  popular: boolean
  badge?: string
  /** Empresa se cotiza: "desde $X" y botón de contacto en vez de checkout */
  custom?: boolean
  tagline: string
  features: string[]
  /** Lo que distingue a este plan del anterior (se resalta en la UI) */
  highlightFeatures?: string[]
}

/** Incluido en TODOS los planes — es el argumento de venta, no un extra. */
export const INCLUDED_IN_ALL = [
  'Portal del cliente (la app de tu negocio)',
  'Notificaciones web ilimitadas y gratis',
  'Citas, pedidos y cupones',
]

/** Lo que el negocio paga aparte, dicho claro desde el principio. */
export const META_FEES_NOTE =
  'Los cargos de WhatsApp los cobra Meta directo en tu cuenta. IaRadio te ayuda a pagar menos: ' +
  'tus clientes reciben recordatorios y promociones gratis por la app de tu negocio.'

export const PLANS_CONFIG: PlanDefinition[] = [
  {
    key: 'starter',
    name: 'Arranque',
    price_mxn: 449,
    price_usd: 26,
    messages: 150,
    conversations: 300,
    days: 30,
    popular: false,
    tagline: 'Para empezar a atender y vender en automático',
    features: [
      '300 conversaciones del bot al mes',
      '150 envíos de campaña por WhatsApp',
      'Portal del cliente + notificaciones web ilimitadas',
      'Bot IA 24/7 con tus instrucciones',
      'Citas, pedidos y cupones',
      '1 usuario',
    ],
  },
  {
    key: 'growth',
    name: 'Negocio',
    price_mxn: 899,
    price_usd: 52,
    messages: 500,
    conversations: 1000,
    days: 30,
    popular: true,
    badge: '⭐ Más popular',
    tagline: 'Para el negocio que ya vende todos los días',
    features: [
      '1,000 conversaciones del bot al mes',
      '500 envíos de campaña por WhatsApp',
      'Portal del cliente + notificaciones web ilimitadas',
      'Bot que conoce tu catálogo e información',
      'Banners y flyers con IA',
      '4 cuñas de radio con IA al mes',
      'Automatizaciones',
      '2 usuarios',
    ],
    highlightFeatures: [
      'Bot que conoce tu catálogo e información',
      '4 cuñas de radio con IA al mes',
      'Automatizaciones',
    ],
  },
  {
    key: 'pro',
    name: 'Crecimiento',
    price_mxn: 1799,
    price_usd: 104,
    messages: 1500,
    conversations: 3000,
    days: 30,
    popular: false,
    tagline: 'Para crecer con equipo y campañas avanzadas',
    features: [
      '3,000 conversaciones del bot al mes',
      '1,500 envíos de campaña por WhatsApp',
      'Todo lo de Negocio',
      '15 cuñas de radio con IA al mes',
      'Campañas secuencia y saga',
      'Pruebas A/B de mensajes',
      'API de integración',
      '5 usuarios',
    ],
    highlightFeatures: ['15 cuñas de radio con IA al mes', 'Pruebas A/B de mensajes', 'API de integración'],
  },
  {
    key: 'enterprise',
    name: 'Empresa',
    price_mxn: 4999,
    price_usd: 289,
    messages: 5000,
    conversations: -1,
    days: 30,
    popular: false,
    custom: true,
    tagline: 'Para cadenas, franquicias y operaciones grandes',
    features: [
      'Conversaciones y envíos a la medida',
      'Todo lo de Crecimiento',
      'Cuñas de radio sin límite',
      'Tu marca (white-label)',
      'Usuarios sin límite',
      'Acompañamiento en la puesta en marcha',
    ],
    highlightFeatures: ['Tu marca (white-label)', 'Conversaciones y envíos a la medida'],
  },
]

/** Paquetes extra de pago único — deben coincidir con ADDONS en el backend. */
export const ADDONS_CONFIG = [
  { key: 'conversations_500', name: '+500 conversaciones del bot', price_mxn: 149, note: 'No vencen' },
  { key: 'messages_500', name: '+500 envíos de campaña', price_mxn: 99, note: 'Se suman a tu saldo' },
] as const

/** Mapa rápido key → plan */
export const PLANS_MAP = Object.fromEntries(PLANS_CONFIG.map((p) => [p.key, p])) as Record<PlanKey, PlanDefinition>

/** Nombre de venta de cualquier plan, incluidos los retirados (micro/business) y la prueba. */
export function planDisplayName(key: string | null | undefined): string {
  if (!key || key === 'trial') return 'Prueba gratis'
  if (key === 'micro') return 'Micro (anterior)'
  if (key === 'business') return 'Business (anterior)'
  return PLANS_MAP[key as PlanKey]?.name ?? key
}

/** Planes que se muestran en la landing (Empresa va aparte, como "cotiza"). */
export const LANDING_PLANS = PLANS_CONFIG.filter((p) => !p.custom)
