// Campaña en 3 toques (docs/specs/2026-10-28-campana-3-toques.md): lo que no
// es pantalla, aparte para poder probarlo.

export type Audience = 'all' | 'bought' | 'one'
export type Discount = 0 | 10 | 15 | 20

// "Los que compraron": un "Cobré" o pedido cobrado en los últimos 90 días.
export const BOUGHT_DAYS = 90

export interface QuickReach {
  total: number
  web: number
  web_silent: number
  web_chat: number
  whatsapp: number
  whatsapp_cost_mxn: number
  whatsapp_connected: boolean
  whatsapp_unreachable: number
}

export function audienceSegment(audience: Audience, contactId: string | null): Record<string, unknown> {
  if (audience === 'bought') return { bought_days: BOUGHT_DAYS }
  if (audience === 'one') return contactId ? { specific_contacts: [contactId] } : { specific_contacts: [] }
  return {}
}

// Nombre corto para la lista de campañas, sacado de lo que pidió el dueño.
export function campaignName(intent: string): string {
  const clean = intent.trim().replace(/\s+/g, ' ')
  const name = clean.charAt(0).toUpperCase() + clean.slice(1)
  return name.length > 60 ? `${name.slice(0, 57).trimEnd()}…` : name
}

export function buildCampaignBody(intent: string, message: string, audience: Audience, contactId: string | null, discount: Discount) {
  return {
    name: campaignName(intent),
    type: 'promo',
    message_text: message.trim(),
    segment: audienceSegment(audience, contactId),
    ab_test: {
      enabled: false,
      campaign_mode: 'regular',
      // El cupón solo va si el dueño tocó un descuento.
      ...(discount ? { has_coupon: true, coupon_description: `${discount}% de descuento`, coupon_percent: discount, coupon_hours: 72 } : {}),
    },
    status: 'draft',
  }
}

// Como lo verá el cliente: las variables con un ejemplo.
export function previewText(message: string, businessName: string): string {
  return message
    .replace(/\{\{nombre\}\}/g, 'María López')
    .replace(/\{\{primer_nombre\}\}/g, 'María')
    .replace(/\{\{ciudad\}\}/g, 'Tlaxiaco')
    .replace(/\{\{negocio\}\}/g, businessName || 'tu negocio')
}

const clientes = (n: number) => `${n.toLocaleString('es-MX')} ${n === 1 ? 'cliente' : 'clientes'}`

/** "A 3 clientes les suena aviso · 12 clientes la ven en su chat cuando entren", para "Mandar gratis por web". */
export function webReachLine(r: QuickReach): string {
  const ring = r.web - r.web_silent
  const chat = r.web_silent + r.web_chat
  const parts: string[] = []
  if (ring > 0) parts.push(`A ${clientes(ring)} ${ring === 1 ? 'le' : 'les'} suena aviso`)
  if (chat > 0) parts.push(`${clientes(chat)} ${chat === 1 ? 'la ve en su chat cuando entre' : 'la ven en su chat cuando entren'}`)
  return parts.join(' · ')
}

/** El % que el texto le promete al cliente ("10% en cargadores" → 10), o null.
 * Sirve para avisar si el texto promete un descuento que el cupón no da. */
export function promisedPercent(message: string): number | null {
  const m = message.match(/(?<!\d)(\d{1,3})\s?%/)
  return m ? Number(m[1]) : null
}

/** Aviso cuando el texto y el cupón no cuadran (prueba real 2026-10-28: el
 * texto decía "10%" y salió sin cupón), o null si cuadran. */
export function discountMismatch(message: string, discount: Discount): string | null {
  const promised = promisedPercent(message)
  if (promised === null || promised === discount) return null
  if (!discount) return `Tu mensaje dice ${promised}%, pero no lleva cupón: el cliente no tendrá con qué cobrarlo.`
  return `Tu mensaje dice ${promised}%, pero el cupón es de ${discount}%.`
}

export function pesos(n: number): string {
  // Montos en pesos: $5, no $5.00.
  const digits = Number.isInteger(n) ? 0 : 2
  return n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN', minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function audienceEmptyReason(audience: Audience, contactId: string | null, reach: QuickReach | undefined): string | null {
  if (audience === 'one' && !contactId) return 'Escoge a quién se la mandas.'
  if (!reach || reach.web + reach.web_chat > 0) return null
  if (audience === 'bought') return `Nadie te ha comprado en los últimos ${BOUGHT_DAYS} días (con "Cobré" o pedido).`
  return 'Todavía no tienes clientes a quién mandarle la promo.'
}

/** Cuándo sale una promo mandada de noche o en domingo (el envío espera al
 * horario humano, 8 am a 9 pm de lunes a sábado): "mañana a las 8:00 a.m.". */
export function startsAtLabel(iso: string, now: Date = new Date()): string {
  const tz = 'America/Mexico_City'
  const day = (d: Date) => d.toLocaleDateString('en-CA', { timeZone: tz })
  const at = new Date(iso)
  const hour = at.toLocaleTimeString('es-MX', { timeZone: tz, hour: 'numeric', minute: '2-digit' })
  const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000)
  const when = day(at) === day(now) ? 'hoy'
    : day(at) === day(tomorrow) ? 'mañana'
    : `el ${at.toLocaleDateString('es-MX', { timeZone: tz, weekday: 'long' })}`
  return `${when} a las ${hour}`
}
