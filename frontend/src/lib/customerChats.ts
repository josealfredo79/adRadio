import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { chatSeenAt } from '@/lib/customerAccount'

// La lista de chats del cliente (/mi y el panel izquierdo en computadora).
const TZ = 'America/Mexico_City'

export interface MyBusiness {
  portal_path: string
  name: string
  logo_url: string
  color: string
  city: string
  loyalty: { stamps: number; required: number; reward: string; rewards_ready: number } | null
  next_appointment: { service: string; scheduled_at: string } | null
  coupons: number
  agent?: string
  last_message: { text: string; at: string | null; from_me: boolean } | null
}

const dayKey = (d: Date) => new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(d)

// Como WhatsApp: hora si fue hoy, "ayer", el día de la semana o la fecha.
export function chatTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  if (dayKey(d) === dayKey(now)) return new Intl.DateTimeFormat('es-MX', { hour: 'numeric', minute: '2-digit', timeZone: TZ }).format(d)
  if (dayKey(d) === dayKey(new Date(now.getTime() - 86400000))) return 'ayer'
  if (now.getTime() - d.getTime() < 6 * 86400000)
    return new Intl.DateTimeFormat('es-MX', { weekday: 'short', timeZone: TZ }).format(d).replace('.', '')
  return new Intl.DateTimeFormat('es-MX', { day: 'numeric', month: 'short', timeZone: TZ }).format(d).replace('.', '')
}

export const portalToken = (path: string) => path.replace(/^\/c\//, '')

export function isUnread(b: MyBusiness): boolean {
  const m = b.last_message
  if (!m || m.from_me || !m.at) return false
  const seen = chatSeenAt(portalToken(b.portal_path))
  return !seen || new Date(m.at) > new Date(seen)
}

// Sin mensajes todavía: lo útil de ese negocio en una línea.
export function idlePreview(b: MyBusiness): string {
  if (b.loyalty?.rewards_ready) return `🎁 ¡Tu premio está listo! ${b.loyalty.reward}`
  if (b.next_appointment) return `📅 ${b.next_appointment.service}`
  if (b.coupons) return `🎫 Tienes ${b.coupons} ${b.coupons === 1 ? 'cupón' : 'cupones'}`
  if (b.loyalty) return `🎟️ ${b.loyalty.stamps} de ${b.loyalty.required} sellos`
  return 'Toca para platicar'
}

export function useMyBusinesses(token: string | null, onExpired?: () => void) {
  const query = useQuery<{ businesses: MyBusiness[] }>({
    queryKey: ['my-businesses', token],
    queryFn: () => api.get('/public/me/businesses', { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.data),
    enabled: !!token,
    retry: false,
    // Mensajes nuevos de los negocios mientras la lista está abierta.
    refetchInterval: 30000,
  })
  // Sesión vencida o inválida: de vuelta a entrar con el número.
  useEffect(() => {
    const status = (query.error as { response?: { status?: number } } | null)?.response?.status
    if (status === 401) onExpired?.()
  }, [query.error, onExpired])
  return query
}
