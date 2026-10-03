import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import SEO from '@/components/SEO'
import {
  ArrowLeft,
  Bell,
  BellOff,
  CalendarDays,
  Check,
  ChevronDown,
  Copy,
  Gift,
  MessageCircle,
  Mic,
  Send,
  ShoppingBag,
  Sparkles,
  Store,
  Share,
  Square,
  Ticket,
  Volume2,
  VolumeX,
  X,
} from 'lucide-react'
import { getSiteTheme, isDarkTheme, type SiteThemeDef } from '@/pages/publicSite/theme'
import { waDigits } from '@/pages/publicSite/utils'
import { MeshBackground, cardElevationStyle } from '@/pages/publicSite/components'
import { PUBLIC_SITE_STYLES } from '@/pages/publicSite/styles'
import { useSpeaker } from '@/lib/useSpeaker'
import { canRecordVoice, startVoiceRecording, type VoiceSession } from '@/lib/voiceRecorder'

// La cabeza que habla solo se descarga si el cliente usa la voz.
const MeshHead3D = lazy(() => import('@/components/MeshHead3D'))

// Portal del cliente (/c/:token) y página de una promo (/c/:token/promo/:promoId).
// El token es la credencial (ver backend/app/services/portal_service.py): sin
// login, solo lo de este cliente. Todo lo que pasa aquí — ver citas, cancelar,
// platicar con el bot — es gratis; por WhatsApp cada mensaje lo cobra Meta.

interface Business {
  advertiser_id: string
  name: string
  logo_url: string
  color: string
  site_theme: string
  slug: string
  city: string
  agent: string
  whatsapp_number: string
}

interface PortalAppointment {
  id: string
  service: string
  scheduled_at: string
  duration_min: number
  status: string
  can_cancel: boolean
}

interface PortalOrder {
  id: string
  order_number: number
  state: string
  state_label: string
  items: string
  payment_method: string
  created_at: string | null
}

interface PortalCoupon {
  code: string
  description: string
  discount_type: string
  discount_value: string
  expires_at: string
}

interface PromoSummary {
  id: string
  title: string
  excerpt: string
  image_url: string
  has_coupon: boolean
}

interface PromoDetail {
  id: string
  title: string
  text: string
  image_url: string
  coupon: PortalCoupon | null
}

interface PortalPush {
  available: boolean
  public_key: string
  subscribed_devices: number
}

interface PortalData {
  push: PortalPush
  business: Business
  customer: { first_name: string }
  promotions: PromoSummary[]
  upcoming_appointments: PortalAppointment[]
  past_appointments: PortalAppointment[]
  orders: PortalOrder[]
  coupons: PortalCoupon[]
}

const TZ = 'America/Mexico_City'

const fmtDay = (iso: string) =>
  new Intl.DateTimeFormat('es-MX', { weekday: 'long', day: 'numeric', month: 'long', timeZone: TZ }).format(new Date(iso))
const fmtTime = (iso: string) =>
  new Intl.DateTimeFormat('es-MX', { hour: 'numeric', minute: '2-digit', timeZone: TZ }).format(new Date(iso))
const fmtShort = (iso: string) =>
  new Intl.DateTimeFormat('es-MX', { day: 'numeric', month: 'short', timeZone: TZ }).format(new Date(iso))
const dayNum = (iso: string) => new Intl.DateTimeFormat('es-MX', { day: 'numeric', timeZone: TZ }).format(new Date(iso))
const monthShort = (iso: string) =>
  new Intl.DateTimeFormat('es-MX', { month: 'short', timeZone: TZ }).format(new Date(iso)).replace('.', '')

function discountLabel(c: PortalCoupon): string {
  const value = Number(c.discount_value)
  const n = Number.isInteger(value) ? String(value) : value.toFixed(2)
  if (c.discount_type === 'percentage' && value > 0) return `${n}% de descuento`
  if (c.discount_type === 'fixed' && value > 0) return `$${n} de descuento`
  return c.description || 'Regalo para ti'
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'Por confirmar',
  confirmed: 'Confirmada',
  completed: 'Atendida',
  cancelled: 'Cancelada',
  no_show: 'No asististe',
}

export default function PortalPage() {
  const { token, promoId } = useParams<{ token: string; promoId?: string }>()
  const [chatPrefill, setChatPrefill] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState(false)

  const { data, isLoading, isError } = useQuery<PortalData>({
    queryKey: ['portal', token],
    queryFn: () => api.get(`/public/portal/${token}`).then((r) => r.data),
    enabled: !!token,
    retry: false,
  })

  // El index.html trae el manifest del dashboard; aquí va uno por cliente para
  // que "Agregar a inicio" instale la app del negocio (requisito en iPhone
  // para recibir avisos). Se restaura al salir.
  useEffect(() => {
    if (!data || !token) return
    const link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]')
    const previous = link?.href
    if (link) link.href = `/api/v1/public/portal/${token}/manifest.webmanifest`
    return () => {
      if (link && previous) link.href = previous
    }
  }, [data, token])

  // ?n=<message_id>: llegó tocando una notificación de campaña — contarla
  // como "leída" y limpiar la URL para que recargar no la cuente dos veces.
  useEffect(() => {
    if (!token) return
    const params = new URLSearchParams(window.location.search)
    const n = params.get('n')
    if (!n) return
    api.post(`/public/portal/${token}/opened`, { message_id: n }).catch(() => {})
    params.delete('n')
    const qs = params.toString()
    window.history.replaceState(null, '', window.location.pathname + (qs ? `?${qs}` : ''))
  }, [token])

  const openChat = (prefill?: string) => {
    setChatPrefill(prefill ?? null)
    setChatOpen(true)
  }

  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center bg-[#06060f] text-white/70">Cargando…</div>
  }

  if (isError || !data) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-[#06060f] px-6 text-center text-white">
        <p className="text-2xl font-bold">Este link ya no es válido</p>
        <p className="text-white/60 max-w-sm">Pídele al negocio que te mande uno nuevo por WhatsApp.</p>
      </div>
    )
  }

  const theme = getSiteTheme(data.business.site_theme)
  const dark = isDarkTheme(theme)
  const color = data.business.color

  return (
    <>
      <SEO title={`Tu espacio en ${data.business.name}`} noIndex />
      <style>{PUBLIC_SITE_STYLES}</style>
      <div className="min-h-screen font-sans pb-28" style={{ background: theme.bg, color: theme.text }}>
        <MeshBackground color={color} dark={dark} />
        <div className="relative z-10 mx-auto max-w-lg px-4 pt-6">
          <BusinessHeader business={data.business} theme={theme} />
          {promoId ? (
            <PromoView token={token!} promoId={promoId} business={data.business} theme={theme} onWant={openChat} />
          ) : (
            <PortalHome token={token!} data={data} theme={theme} onChat={openChat} />
          )}
          <p className="mt-10 text-center text-xs" style={{ color: theme.muted }}>
            Hecho con <span className="font-semibold">IaRadio</span>
          </p>
        </div>

        {!chatOpen && (
          <button
            onClick={() => openChat()}
            className="fixed bottom-5 right-5 z-20 inline-flex items-center gap-2 rounded-full px-5 py-3.5 text-sm font-semibold text-white shadow-xl transition-transform hover:scale-[1.03] active:scale-[0.98]"
            style={{ background: color, boxShadow: `0 10px 30px ${color}55` }}
          >
            <MessageCircle size={18} />
            Platicar con {data.business.agent}
          </button>
        )}
        {chatOpen && (
          <ChatSheet
            token={token!}
            promoId={promoId}
            business={data.business}
            theme={theme}
            prefill={chatPrefill}
            onClose={() => setChatOpen(false)}
          />
        )}
      </div>
    </>
  )
}

function BusinessHeader({ business, theme }: { business: Business; theme: SiteThemeDef }) {
  return (
    <header className="flex items-center gap-3">
      {business.logo_url ? (
        <img src={business.logo_url} alt="" className="h-11 w-11 rounded-xl object-cover" />
      ) : (
        <div
          className="h-11 w-11 rounded-xl flex items-center justify-center text-lg font-bold text-white"
          style={{ background: `linear-gradient(135deg, ${business.color}, ${business.color}99)` }}
        >
          {(business.name || '?')[0].toUpperCase()}
        </div>
      )}
      <div className="min-w-0">
        <p className="font-semibold leading-tight truncate">{business.name}</p>
        {business.city && (
          <p className="text-xs" style={{ color: theme.muted }}>
            {business.city}
          </p>
        )}
      </div>
    </header>
  )
}

function Card({ theme, children, className = '' }: { theme: SiteThemeDef; children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-2xl ${className}`}
      style={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, ...cardElevationStyle(theme) }}
    >
      {children}
    </div>
  )
}

function SectionTitle({ icon, title, color }: { icon: React.ReactNode; title: string; color: string }) {
  return (
    <h2 className="mt-8 mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wide">
      <span style={{ color }}>{icon}</span>
      {title}
    </h2>
  )
}

function PortalHome({
  token,
  data,
  theme,
  onChat,
}: {
  token: string
  data: PortalData
  theme: SiteThemeDef
  onChat: (prefill?: string) => void
}) {
  const { business } = data
  const color = business.color
  const [showHistory, setShowHistory] = useState(false)

  return (
    <main>
      <section className="mt-8">
        <h1 className="text-3xl font-bold tracking-tight">
          Hola{data.customer.first_name ? `, ${data.customer.first_name}` : ''} 👋
        </h1>
        <p className="mt-2 text-[15px] leading-relaxed" style={{ color: theme.muted }}>
          Aquí tienes todo lo tuyo con {business.name}: citas, pedidos y promociones, sin esperar respuesta.
        </p>
      </section>

      <div className="mt-6 grid grid-cols-3 gap-2">
        <QuickAction theme={theme} color={color} icon={<CalendarDays size={20} />} label="Agendar" onClick={() => onChat('Quiero agendar una cita')} />
        {business.slug ? (
          <QuickAction theme={theme} color={color} icon={<Store size={20} />} label="Catálogo" href={`/sitio/${business.slug}#catalogo`} />
        ) : (
          <QuickAction theme={theme} color={color} icon={<ShoppingBag size={20} />} label="Pedir" onClick={() => onChat('Quiero hacer un pedido')} />
        )}
        {/* Antes era "WhatsApp" (wa.me): mandaba al cliente de regreso al canal
            que Meta cobra. El chat de aquí hace lo mismo, con voz, y es gratis. */}
        <QuickAction theme={theme} color={color} icon={<Mic size={20} />} label="Preguntar" onClick={() => onChat()} />
      </div>

      {data.push.available && (
        <NotifyCard
          token={token}
          push={data.push}
          theme={theme}
          color={color}
          hasUpcoming={data.upcoming_appointments.length > 0}
        />
      )}

      {data.promotions.length > 0 && (
        <>
          <SectionTitle icon={<Gift size={16} />} title="Promociones para ti" color={color} />
          <div className="space-y-3">
            {data.promotions.map((p) => (
              <Link key={p.id} to={`/c/${token}/promo/${p.id}`} className="block transition-transform hover:scale-[1.01]">
                <Card theme={theme} className="overflow-hidden">
                  {p.image_url && <img src={p.image_url} alt="" className="h-40 w-full object-cover" />}
                  <div className="p-4">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-semibold">{p.title}</p>
                      {p.has_coupon && (
                        <span className="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold text-white" style={{ background: color }}>
                          Con cupón
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm" style={{ color: theme.muted }}>
                      {p.excerpt}
                    </p>
                    <p className="mt-3 text-sm font-semibold" style={{ color }}>
                      Ver promo →
                    </p>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        </>
      )}

      <SectionTitle icon={<CalendarDays size={16} />} title="Tus próximas citas" color={color} />
      {data.upcoming_appointments.length ? (
        <div className="space-y-3">
          {data.upcoming_appointments.map((a) => (
            <AppointmentCard key={a.id} token={token} appt={a} theme={theme} color={color} />
          ))}
        </div>
      ) : (
        <EmptyState theme={theme} text="No tienes citas próximas." cta="Agendar una cita" color={color} onClick={() => onChat('Quiero agendar una cita')} />
      )}

      {data.coupons.length > 0 && (
        <>
          <SectionTitle icon={<Ticket size={16} />} title="Tus cupones" color={color} />
          <div className="space-y-3">
            {data.coupons.map((c) => (
              <CouponTicket key={c.code} coupon={c} theme={theme} color={color} />
            ))}
          </div>
        </>
      )}

      <SectionTitle icon={<ShoppingBag size={16} />} title="Tus pedidos" color={color} />
      {data.orders.length ? (
        <Card theme={theme}>
          {data.orders.map((o, i) => (
            <div
              key={o.id}
              className="flex items-start justify-between gap-3 p-4"
              style={i ? { borderTop: `1px solid ${theme.cardBorder}` } : undefined}
            >
              <div className="min-w-0">
                <p className="text-sm font-semibold">Pedido #{String(o.order_number).padStart(4, '0')}</p>
                <p className="mt-0.5 text-sm truncate" style={{ color: theme.muted }}>
                  {o.items || 'Sin detalle'}
                </p>
                {o.created_at && (
                  <p className="mt-0.5 text-xs" style={{ color: theme.muted }}>
                    {fmtShort(o.created_at)}
                  </p>
                )}
              </div>
              <StatusChip label={o.state_label} tone={o.state === 'confirmed' ? 'good' : o.state === 'cancelled' ? 'bad' : 'wait'} />
            </div>
          ))}
        </Card>
      ) : (
        <EmptyState theme={theme} text="Aún no tienes pedidos." cta="Hacer un pedido" color={color} onClick={() => onChat('Quiero hacer un pedido')} />
      )}

      {data.past_appointments.length > 0 && (
        <div className="mt-8">
          <button
            onClick={() => setShowHistory((v) => !v)}
            className="flex w-full items-center justify-between text-sm font-semibold"
            style={{ color: theme.muted }}
          >
            Historial de citas
            <ChevronDown size={16} className={`transition-transform ${showHistory ? 'rotate-180' : ''}`} />
          </button>
          {showHistory && (
            <Card theme={theme} className="mt-3">
              {data.past_appointments.map((a, i) => (
                <div
                  key={a.id}
                  className="flex items-center justify-between gap-3 p-4 text-sm"
                  style={i ? { borderTop: `1px solid ${theme.cardBorder}` } : undefined}
                >
                  <div>
                    <p className="font-medium">{a.service}</p>
                    <p className="text-xs" style={{ color: theme.muted }}>
                      {fmtShort(a.scheduled_at)}
                    </p>
                  </div>
                  <span className="text-xs" style={{ color: theme.muted }}>
                    {STATUS_LABEL[a.status] ?? a.status}
                  </span>
                </div>
              ))}
            </Card>
          )}
        </div>
      )}
    </main>
  )
}

function QuickAction({
  theme,
  color,
  icon,
  label,
  onClick,
  href,
  external,
}: {
  theme: SiteThemeDef
  color: string
  icon: React.ReactNode
  label: string
  onClick?: () => void
  href?: string
  external?: boolean
}) {
  const body = (
    <Card theme={theme} className="flex flex-col items-center gap-1.5 py-4 transition-transform hover:scale-[1.03] active:scale-[0.98]">
      <span style={{ color }}>{icon}</span>
      <span className="text-xs font-semibold">{label}</span>
    </Card>
  )
  if (href && external) return <a href={href} target="_blank" rel="noreferrer">{body}</a>
  if (href) return <Link to={href}>{body}</Link>
  return <button onClick={onClick} className="text-left">{body}</button>
}

function StatusChip({ label, tone }: { label: string; tone: 'good' | 'wait' | 'bad' }) {
  const styles = {
    good: 'bg-emerald-500/15 text-emerald-500',
    wait: 'bg-amber-500/15 text-amber-500',
    bad: 'bg-rose-500/15 text-rose-500',
  }[tone]
  return <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${styles}`}>{label}</span>
}

function EmptyState({
  theme,
  text,
  cta,
  color,
  onClick,
}: {
  theme: SiteThemeDef
  text: string
  cta: string
  color: string
  onClick: () => void
}) {
  return (
    <Card theme={theme} className="flex items-center justify-between gap-3 p-4">
      <p className="text-sm" style={{ color: theme.muted }}>
        {text}
      </p>
      <button onClick={onClick} className="shrink-0 text-sm font-semibold" style={{ color }}>
        {cta} →
      </button>
    </Card>
  )
}

function AppointmentCard({ token, appt, theme, color }: { token: string; appt: PortalAppointment; theme: SiteThemeDef; color: string }) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const confirmAttendance = async () => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post(`/public/portal/${token}/appointments/${appt.id}/confirm`)
      queryClient.setQueryData<PortalData>(['portal', token], (old) =>
        old && {
          ...old,
          upcoming_appointments: old.upcoming_appointments.map((a) => (a.id === appt.id ? data.appointment : a)),
        },
      )
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || 'No se pudo confirmar. Intenta de nuevo.')
    } finally {
      setBusy(false)
    }
  }

  const cancel = async () => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post(`/public/portal/${token}/appointments/${appt.id}/cancel`)
      // Moverla al historial ya, sin esperar el refetch — la confirmación del
      // servidor es suficiente y en un celular con mala señal el refetch tarda.
      queryClient.setQueryData<PortalData>(['portal', token], (old) =>
        old && {
          ...old,
          upcoming_appointments: old.upcoming_appointments.filter((a) => a.id !== appt.id),
          past_appointments: [data.appointment, ...old.past_appointments],
        },
      )
      queryClient.invalidateQueries({ queryKey: ['portal', token] })
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || 'No se pudo cancelar. Intenta de nuevo.')
      setBusy(false)
      setConfirming(false)
    }
  }

  return (
    <Card theme={theme} className="p-4">
      <div className="flex gap-4">
        <div
          className="flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-xl text-white"
          style={{ background: `linear-gradient(135deg, ${color}, ${color}aa)` }}
        >
          <span className="text-xl font-bold leading-none">{dayNum(appt.scheduled_at)}</span>
          <span className="text-[11px] uppercase">{monthShort(appt.scheduled_at)}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <p className="font-semibold">{appt.service}</p>
            <StatusChip label={STATUS_LABEL[appt.status] ?? appt.status} tone={appt.status === 'confirmed' ? 'good' : 'wait'} />
          </div>
          <p className="mt-0.5 text-sm capitalize" style={{ color: theme.muted }}>
            {fmtDay(appt.scheduled_at)} · {fmtTime(appt.scheduled_at)}
          </p>
        </div>
      </div>
      {appt.can_cancel && (
        <div className="mt-3 pt-3" style={{ borderTop: `1px solid ${theme.cardBorder}` }}>
          {confirming ? (
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm">¿Seguro que la cancelas?</span>
              <div className="flex gap-2">
                <button
                  onClick={() => setConfirming(false)}
                  disabled={busy}
                  className="rounded-full px-3 py-1.5 text-sm font-semibold"
                  style={{ border: `1px solid ${theme.cardBorder}` }}
                >
                  No
                </button>
                <button
                  onClick={cancel}
                  disabled={busy}
                  className="rounded-full bg-rose-500 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
                >
                  {busy ? 'Cancelando…' : 'Sí, cancelar'}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2">
              <button onClick={() => setConfirming(true)} className="text-sm font-semibold text-rose-500">
                Cancelar cita
              </button>
              {appt.status === 'pending' && (
                <button
                  onClick={confirmAttendance}
                  disabled={busy}
                  className="rounded-full px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
                  style={{ background: color }}
                >
                  {busy ? 'Confirmando…' : 'Confirmar asistencia'}
                </button>
              )}
            </div>
          )}
          {error && <p className="mt-2 text-sm text-rose-500">{error}</p>}
        </div>
      )}
    </Card>
  )
}

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padded = (base64 + '='.repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0))
}

type NotifyState = 'loading' | 'unsupported' | 'ios-install' | 'denied' | 'off' | 'on'

function detectNotifyState(): NotifyState | Promise<NotifyState> {
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent)
  const standalone =
    window.matchMedia?.('(display-mode: standalone)').matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  const supported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
  // En iPhone, Safari solo ofrece push a la app ya agregada a la pantalla de inicio.
  if (ios && !standalone) return 'ios-install'
  if (!supported) return 'unsupported'
  if (Notification.permission === 'denied') return 'denied'
  return navigator.serviceWorker
    .getRegistration('/c/')
    .then((reg) => reg?.pushManager.getSubscription())
    .then((sub): NotifyState => (sub ? 'on' : 'off'))
    .catch((): NotifyState => 'off')
}

// "¿Te aviso?" — avisos gratis (Web Push) en vez de WhatsApp cobrado. El
// mejor momento para pedirlo es con una cita en puerta: el recordatorio de
// mañana es la razón concreta para aceptar.
function NotifyCard({
  token,
  push,
  theme,
  color,
  hasUpcoming,
}: {
  token: string
  push: PortalPush
  theme: SiteThemeDef
  color: string
  hasUpcoming: boolean
}) {
  const [state, setState] = useState<NotifyState>('loading')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    Promise.resolve(detectNotifyState()).then((s) => alive && setState(s))
    return () => {
      alive = false
    }
  }, [])

  const enable = async () => {
    setBusy(true)
    setError(null)
    try {
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') {
        setState(permission === 'denied' ? 'denied' : 'off')
        return
      }
      await navigator.serviceWorker.register('/portal-sw.js', { scope: '/c/' })
      const reg = await navigator.serviceWorker.ready
      const sub =
        (await reg.pushManager.getSubscription()) ??
        (await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(push.public_key) as BufferSource,
        }))
      await api.post(`/public/portal/${token}/push/subscribe`, sub.toJSON())
      setState('on')
    } catch {
      setError('No se pudieron activar. Intenta de nuevo en un momento.')
    } finally {
      setBusy(false)
    }
  }

  const disable = async () => {
    setBusy(true)
    try {
      const reg = await navigator.serviceWorker.getRegistration('/c/')
      const sub = await reg?.pushManager.getSubscription()
      if (sub) {
        await api.post(`/public/portal/${token}/push/unsubscribe`, { endpoint: sub.endpoint })
        await sub.unsubscribe()
      }
      setState('off')
    } finally {
      setBusy(false)
    }
  }

  if (state === 'loading' || state === 'unsupported') return null

  const pitch = hasUpcoming ? '¿Te aviso un día antes de tu cita?' : '¿Te aviso de promociones y cupones?'

  return (
    <Card theme={theme} className="mt-6 p-4">
      <div className="flex items-start gap-3">
        <span
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
          style={{ background: `${color}1f`, color }}
        >
          {state === 'denied' ? <BellOff size={20} /> : <Bell size={20} />}
        </span>
        <div className="min-w-0 flex-1">
          {state === 'on' && (
            <>
              <p className="font-semibold">Avisos activados en este celular ✓</p>
              <p className="mt-0.5 text-sm" style={{ color: theme.muted }}>
                Te llegarán tus recordatorios y promociones aquí.
              </p>
              <button onClick={disable} disabled={busy} className="mt-2 text-sm font-semibold" style={{ color: theme.muted }}>
                Desactivar
              </button>
            </>
          )}
          {state === 'off' && (
            <>
              <p className="font-semibold">{pitch}</p>
              <p className="mt-0.5 text-sm" style={{ color: theme.muted }}>
                Te llega directo a tu celular, como una app. Puedes quitarlo cuando quieras.
              </p>
              <button
                onClick={enable}
                disabled={busy}
                className="mt-3 rounded-full px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
                style={{ background: color }}
              >
                {busy ? 'Activando…' : 'Sí, avísame'}
              </button>
            </>
          )}
          {state === 'denied' && (
            <>
              <p className="font-semibold">Los avisos están bloqueados</p>
              <p className="mt-0.5 text-sm" style={{ color: theme.muted }}>
                Para activarlos, permite las notificaciones de este sitio en los ajustes de tu navegador.
              </p>
            </>
          )}
          {state === 'ios-install' && (
            <>
              <p className="font-semibold">{pitch}</p>
              <p className="mt-0.5 text-sm" style={{ color: theme.muted }}>
                En iPhone: toca <Share size={14} className="inline -mt-0.5" /> <b>Compartir</b> y luego{' '}
                <b>Agregar a inicio</b>. Abre el ícono nuevo y activa los avisos desde ahí.
              </p>
            </>
          )}
          {error && <p className="mt-2 text-sm text-rose-500">{error}</p>}
        </div>
      </div>
    </Card>
  )
}

function CouponTicket({ coupon, theme, color }: { coupon: PortalCoupon; theme: SiteThemeDef; color: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(coupon.code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard bloqueado (http, iframe) — el código sigue visible para copiarlo a mano
    }
  }
  return (
    <div className="rounded-2xl p-4" style={{ background: `${color}14`, border: `2px dashed ${color}66` }}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold">{discountLabel(coupon)}</p>
          {coupon.description && coupon.discount_type !== 'free_item' && (
            <p className="text-sm" style={{ color: theme.muted }}>
              {coupon.description}
            </p>
          )}
          <p className="mt-1 text-xs" style={{ color: theme.muted }}>
            Vence el {fmtShort(coupon.expires_at)}
          </p>
        </div>
        <button
          onClick={copy}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-xl px-3 py-2 font-mono text-sm font-bold text-white"
          style={{ background: color }}
          aria-label={`Copiar código ${coupon.code}`}
        >
          {coupon.code}
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>
    </div>
  )
}

function PromoView({
  token,
  promoId,
  business,
  theme,
  onWant,
}: {
  token: string
  promoId: string
  business: Business
  theme: SiteThemeDef
  onWant: (prefill?: string) => void
}) {
  const color = business.color
  const { data: promo, isLoading, isError } = useQuery<PromoDetail>({
    queryKey: ['portal-promo', token, promoId],
    queryFn: () => api.get(`/public/portal/${token}/promos/${promoId}`).then((r) => r.data),
    retry: false,
  })
  const waHref = business.whatsapp_number
    ? `https://wa.me/${waDigits(business.whatsapp_number)}?text=${encodeURIComponent(`Hola, me interesa la promo: ${promo?.title ?? ''}`)}`
    : null

  return (
    <main className="mt-6">
      <Link to={`/c/${token}`} className="inline-flex items-center gap-1.5 text-sm" style={{ color: theme.muted }}>
        <ArrowLeft size={16} />
        Volver a tu espacio
      </Link>
      {isLoading && <p className="mt-10 text-center" style={{ color: theme.muted }}>Cargando…</p>}
      {(isError || (!isLoading && !promo)) && (
        <Card theme={theme} className="mt-6 p-6 text-center">
          <p className="font-semibold">Esta promoción ya terminó</p>
          <p className="mt-1 text-sm" style={{ color: theme.muted }}>
            Pero puedes preguntar por las promociones vigentes.
          </p>
          <button onClick={() => onWant('¿Qué promociones tienen ahorita?')} className="mt-4 text-sm font-semibold" style={{ color }}>
            Preguntar →
          </button>
        </Card>
      )}
      {promo && (
        <Card theme={theme} className="mt-4 overflow-hidden">
          {promo.image_url && <img src={promo.image_url} alt="" className="w-full object-cover" />}
          <div className="space-y-4 p-5">
            <h1 className="text-2xl font-bold">{promo.title}</h1>
            <p className="whitespace-pre-line leading-relaxed" style={{ color: theme.muted }}>
              {promo.text}
            </p>
            {promo.coupon && <CouponTicket coupon={promo.coupon} theme={theme} color={color} />}
            <div className="flex flex-col gap-2 pt-1">
              <button
                onClick={() => onWant(`Me interesa la promo: ${promo.title}`)}
                className="inline-flex items-center justify-center gap-2 rounded-full px-5 py-3.5 text-sm font-semibold text-white transition-transform hover:scale-[1.02] active:scale-[0.98]"
                style={{ background: color, boxShadow: `0 10px 30px ${color}44` }}
              >
                <Sparkles size={18} />
                ¡La quiero!
              </button>
              {waHref && (
                <a
                  href={waHref}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 text-sm font-semibold"
                  style={{ border: `1px solid ${theme.cardBorder}` }}
                >
                  <MessageCircle size={18} />
                  Preguntar por WhatsApp
                </a>
              )}
            </div>
          </div>
        </Card>
      )}
    </main>
  )
}

// El bot escribe con formato de WhatsApp (*negrita*, a veces **negrita**);
// en la web los asteriscos se verían tal cual.
function renderChatText(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*\n]+\*\*|\*[^*\n]+\*)/g).map((part, i) => {
    const bold = part.match(/^\*\*([^*\n]+)\*\*$/) ?? part.match(/^\*([^*\n]+)\*$/)
    return bold ? <strong key={i}>{bold[1]}</strong> : part
  })
}

interface ProductCard {
  url: string
  name: string
  price: string | null
  photo_url: string
}

interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
  cards?: ProductCard[]
}

// Para arrancar con un toque (en el celular escribir cuesta más que en WhatsApp).
const QUICK_ASKS = ['¿Qué productos tienen?', '¿Cuál es su horario?', 'Quiero agendar una cita', 'Quiero hacer un pedido']

function ChatSheet({
  token,
  promoId,
  business,
  theme,
  prefill,
  onClose,
}: {
  token: string
  promoId?: string
  business: Business
  theme: SiteThemeDef
  prefill: string | null
  onClose: () => void
}) {
  const color = business.color
  // La sesión se pide al abrir el chat, pero el primer mensaje puede salir
  // antes de que llegue (con texto precargado, el cliente toca Enviar al
  // instante) — y sin esperarla, el mensaje caía en otra sesión sin el
  // contexto de la promo ni el vínculo con el cliente.
  const sessionRef = useRef<Promise<string | null> | null>(null)
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [input, setInput] = useState(prefill ?? '')
  const [sending, setSending] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  // Modo voz: el cliente habla en vez de escribir y el bot le contesta en voz
  // alta, con la cabeza que mueve los labios. Se activa al tocar el micrófono.
  const [voiceMode, setVoiceMode] = useState(false)
  const [recording, setRecording] = useState(false)
  const recorder = useRef<VoiceSession | null>(null)
  const speaker = useSpeaker({ endpoint: `/public/portal/${token}/speak` })
  const micAvailable = canRecordVoice()

  useEffect(() => {
    sessionRef.current = api
      // Desde una promo, el backend le deja al bot el contexto de esa promo y
      // del cupón del cliente, para que "¡La quiero!" no reciba un "¿en qué te ayudo?".
      .post(`/public/portal/${token}/chat-session`, promoId ? { promo_id: promoId } : undefined)
      .then((r) => r.data.session_id as string)
      .catch(() => null)
    inputRef.current?.focus()
  }, [token, promoId])

  useEffect(() => () => recorder.current?.cancel(), [])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns, sending])

  const send = async (text?: string, spoken = voiceMode) => {
    const message = (text ?? input).trim()
    if (!message || sending) return
    if (text === undefined) setInput('')
    setTurns((t) => [...t, { role: 'user', content: message }])
    setSending(true)
    try {
      const sessionId = await sessionRef.current
      const r = await api.post(`/widget/chat/${business.advertiser_id}`, { message, session_id: sessionId })
      sessionRef.current = Promise.resolve(r.data.session_id)
      const reply: string = r.data.reply
      setTurns((t) => [...t, { role: 'assistant', content: reply, cards: r.data.cards ?? [] }])
      if (spoken) void speaker.speak(reply.replace(/https?:\/\/\S+/g, ''))
    } catch {
      setTurns((t) => [...t, { role: 'assistant', content: 'Uy, no me llegó tu mensaje. ¿Lo intentas de nuevo?' }])
    } finally {
      setSending(false)
    }
  }

  const startRecording = async () => {
    speaker.unlock() // dentro del toque: iPhone deja sonar la respuesta después
    speaker.stop()
    setVoiceMode(true)
    try {
      recorder.current = await startVoiceRecording()
      setRecording(true)
    } catch {
      setTurns((t) => [...t, { role: 'assistant', content: 'No pude usar el micrófono. Revisa el permiso o escríbeme 🙏' }])
    }
  }

  const stopRecording = async () => {
    const session = recorder.current
    recorder.current = null
    setRecording(false)
    if (!session) return
    const rec = await session.stop()
    if (rec.seconds < 1) return
    setSending(true)
    try {
      const form = new FormData()
      const ext = rec.mimeType.includes('mp4') ? 'mp4' : rec.mimeType.includes('ogg') ? 'ogg' : 'webm'
      form.append('audio', rec.blob, `voz.${ext}`)
      const r = await api.post(`/public/portal/${token}/listen`, form)
      setSending(false)
      await send(r.data.transcript, true)
    } catch {
      setSending(false)
      setTurns((t) => [...t, { role: 'assistant', content: 'No alcancé a escucharte. ¿Me lo repites o me lo escribes?' }])
    }
  }

  const mood = recording ? 'listening' : sending ? 'thinking' : speaker.speaking ? 'speaking' : 'idle'

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center bg-black/50 sm:items-center" onClick={onClose}>
      <div
        className="flex h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-t-3xl sm:h-[640px] sm:rounded-3xl"
        style={{ background: theme.bg, color: theme.text, border: `1px solid ${theme.cardBorder}` }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: `1px solid ${theme.cardBorder}` }}>
          <div>
            <p className="font-semibold">{business.agent}</p>
            <p className="text-xs" style={{ color: theme.muted }}>
              {business.name} · responde al instante
            </p>
          </div>
          <div className="flex items-center gap-1">
            {voiceMode && (
              <button
                onClick={() => speaker.setMuted(!speaker.muted)}
                aria-label={speaker.muted ? 'Activar la voz' : 'Silenciar la voz'}
                className="rounded-full p-2"
                style={{ color: theme.muted }}
              >
                {speaker.muted ? <VolumeX size={20} /> : <Volume2 size={20} />}
              </button>
            )}
            <button onClick={onClose} aria-label="Cerrar chat" className="rounded-full p-2" style={{ color: theme.muted }}>
              <X size={20} />
            </button>
          </div>
        </div>

        {voiceMode && (
          <div className="flex shrink-0 flex-col items-center bg-[#0a0f2e] pt-1">
            <Suspense fallback={<div style={{ height: 150 }} />}>
              <MeshHead3D mood={mood} getLevel={speaker.level} size={130} />
            </Suspense>
            {/* Crédito que pide la licencia CC BY 3.0 del escaneo de la cabeza */}
            <p className="pb-1 text-[9px] text-white/30">Cabeza 3D: escaneo de Lee Perry-Smith · CC BY 3.0</p>
          </div>
        )}

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {turns.length === 0 && (
            <div className="mx-auto mt-6 max-w-sm text-center">
              <p className="text-sm" style={{ color: theme.muted }}>
                {micAvailable
                  ? 'Pregúntame lo que quieras: escríbeme o toca el micrófono y háblame.'
                  : 'Pregúntame lo que quieras: precios, horarios, agendar o hacer un pedido.'}
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {QUICK_ASKS.map((q) => (
                  <button
                    key={q}
                    onClick={() => void send(q)}
                    className="rounded-full px-3.5 py-2 text-sm"
                    style={{ border: `1px solid ${theme.cardBorder}`, color: theme.text }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {turns.map((t, i) => (
            <div key={i}>
              <div className={`flex ${t.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className="max-w-[85%] whitespace-pre-line rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed"
                  style={
                    t.role === 'user'
                      ? { background: color, color: '#fff', borderBottomRightRadius: 6 }
                      : { background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderBottomLeftRadius: 6 }
                  }
                >
                  {renderChatText(t.content)}
                </div>
              </div>
              {/* Productos que mencionó el bot: foto, precio y "Lo quiero" */}
              {t.cards && t.cards.length > 0 && (
                <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
                  {t.cards.map((c) => (
                    <div
                      key={c.url}
                      className="w-36 shrink-0 overflow-hidden rounded-2xl"
                      style={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}` }}
                    >
                      <a href={c.url} target="_blank" rel="noopener noreferrer">
                        {c.photo_url ? (
                          <img src={c.photo_url} alt={c.name} className="h-24 w-full object-cover" loading="lazy" />
                        ) : (
                          <div className="flex h-24 items-center justify-center" style={{ color: theme.muted }}>
                            <ShoppingBag size={28} />
                          </div>
                        )}
                      </a>
                      <div className="p-2.5">
                        <p className="line-clamp-2 text-sm font-semibold leading-snug">{c.name}</p>
                        {c.price && <p className="text-sm" style={{ color: theme.muted }}>{c.price}</p>}
                        <button
                          onClick={() => void send(`Quiero ${c.name}`)}
                          disabled={sending}
                          className="mt-2 w-full rounded-full py-1.5 text-sm font-semibold text-white disabled:opacity-50"
                          style={{ background: color }}
                        >
                          Lo quiero
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="rounded-2xl px-4 py-2.5 text-sm" style={{ background: theme.cardBg, color: theme.muted }}>
                {voiceMode ? 'Pensando…' : 'Escribiendo…'}
              </div>
            </div>
          )}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            void send(undefined, false)
          }}
          className="flex items-center gap-2 p-3"
          style={{ borderTop: `1px solid ${theme.cardBorder}` }}
        >
          {recording ? (
            <p className="flex-1 px-2 text-[15px]" style={{ color: theme.muted }}>Te escucho… toca el cuadro rojo al terminar</p>
          ) : (
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={500}
              placeholder="Escribe tu mensaje…"
              className="min-w-0 flex-1 rounded-full bg-transparent px-4 py-3 text-[15px] outline-none"
              style={{ border: `1px solid ${theme.cardBorder}`, color: theme.text }}
            />
          )}
          {micAvailable && !input.trim() ? (
            <button
              type="button"
              onClick={() => void (recording ? stopRecording() : startRecording())}
              disabled={sending}
              aria-label={recording ? 'Terminar de hablar' : 'Hablar'}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-white disabled:opacity-50"
              style={{ background: recording ? '#f43f5e' : color }}
            >
              {recording ? <Square size={16} fill="currentColor" /> : <Mic size={20} />}
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim() || sending}
              aria-label="Enviar"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-white disabled:opacity-50"
              style={{ background: color }}
            >
              <Send size={18} />
            </button>
          )}
        </form>
      </div>
    </div>
  )
}
