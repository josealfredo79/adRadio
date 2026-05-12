/**
 * plans.ts — Fuente de verdad única para todos los planes de IaRadio.
 *
 * IMPORTANTE: Cualquier cambio aquí se refleja automáticamente en
 * LandingPage, PlansPage y cualquier otro componente que importe esto.
 * Los precios y mensajes deben coincidir con payments.py en el backend.
 */

export type PlanKey = 'starter' | 'growth' | 'pro' | 'business' | 'enterprise'

export interface PlanDefinition {
  key: PlanKey
  name: string
  price_mxn: number
  price_usd: number
  messages: number
  days: number
  popular: boolean
  badge?: string
  tagline: string
  features: string[]
  /** Features que diferencian hacia arriba (mostradas con color destacado en UI) */
  highlightFeatures?: string[]
}

export const PLANS_CONFIG: PlanDefinition[] = [
  {
    key: 'starter',
    name: 'Starter',
    price_mxn: 499,
    price_usd: 29,
    messages: 200,
    days: 30,
    popular: false,
    tagline: 'Para empezar a vender por WhatsApp',
    features: [
      '200 mensajes/mes',
      'Bot IA 24/7 (respuestas básicas)',
      'Campañas masivas WhatsApp',
      'Importar contactos CSV',
      'Soporte por email',
    ],
  },
  {
    key: 'growth',
    name: 'Growth',
    price_mxn: 999,
    price_usd: 59,
    messages: 500,
    days: 30,
    popular: true,
    badge: '⭐ Más popular',
    tagline: 'El punto dulce para negocios en crecimiento',
    features: [
      '500 mensajes/mes',
      'Bot IA con tu catálogo (RAG)',
      'Campañas masivas + segmentación',
      'Importar contactos CSV',
      'Cupones QR automáticos',
      '3 cuñas de radio con IA/mes',
      'Métricas de campaña (leídos, entregados)',
      'Soporte prioritario por email',
    ],
    highlightFeatures: [
      'Bot IA con tu catálogo (RAG)',
      '3 cuñas de radio con IA/mes',
      'Cupones QR automáticos',
    ],
  },
  {
    key: 'pro',
    name: 'Pro',
    price_mxn: 2499,
    price_usd: 149,
    messages: 1000,
    days: 30,
    popular: false,
    tagline: 'Para negocios que ya quieren escalar',
    features: [
      '1,000 mensajes/mes',
      'Bot IA avanzado con RAG completo',
      'Cuñas de radio ilimitadas con IA',
      'Campañas secuencia (3 mensajes)',
      'Flyers publicitarios con IA',
      'Número dedicado WhatsApp',
      'Métricas avanzadas + cupones',
      'Soporte prioritario (chat + email)',
    ],
    highlightFeatures: [
      'Cuñas de radio ilimitadas con IA',
      'Número dedicado WhatsApp',
      'Campañas secuencia (3 mensajes)',
    ],
  },
  {
    key: 'business',
    name: 'Business',
    price_mxn: 6799,
    price_usd: 399,
    messages: 3000,
    days: 30,
    popular: false,
    tagline: 'Para equipos y franquicias',
    features: [
      '3,000 mensajes/mes',
      'Todo lo de Pro',
      'Campañas saga (4 episodios semanales)',
      'A/B testing de mensajes',
      'Multi-agente IA',
      'Analytics avanzados',
      'API de integración',
      'Gerente de cuenta dedicado',
    ],
    highlightFeatures: [
      'Campañas saga (4 episodios semanales)',
      'A/B testing de mensajes',
      'API de integración',
    ],
  },
  {
    key: 'enterprise',
    name: 'Enterprise',
    price_mxn: 19999,
    price_usd: 1199,
    messages: 10000,
    days: 30,
    popular: false,
    tagline: 'Solución a medida para grandes operaciones',
    features: [
      '10,000 mensajes/mes',
      'Todo lo de Business',
      'Multi-número WhatsApp',
      'White-label (tu marca)',
      'Acceso API completo',
      'SLA garantizado',
      'Gerente de cuenta dedicado',
      'Onboarding personalizado',
    ],
    highlightFeatures: [
      'White-label (tu marca)',
      'Multi-número WhatsApp',
      'SLA garantizado',
    ],
  },
]

/** Mapa rápido key → plan */
export const PLANS_MAP = Object.fromEntries(
  PLANS_CONFIG.map((p) => [p.key, p])
) as Record<PlanKey, PlanDefinition>

/** Solo los planes visibles en la Landing (sin Enterprise que va aparte) */
export const LANDING_PLANS = PLANS_CONFIG.filter((p) => p.key !== 'enterprise')
