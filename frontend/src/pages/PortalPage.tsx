import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import SEO from '@/components/SEO'
import AgentChat from '@/components/AgentChat'
import CustomerDesktopShell from '@/components/CustomerDesktopShell'
import { useIsDesktop } from '@/lib/useIsDesktop'
import { useNativeViewport } from '@/lib/useNativeViewport'
import { markChatSeen, rememberChat } from '@/lib/customerAccount'
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
  ShoppingBag,
  Sparkles,
  Stamp,
  Store,
  Share,
  Ticket,
} from 'lucide-react'
import { getSiteTheme, isDarkTheme, type SiteThemeDef } from '@/pages/publicSite/theme'
import { waDigits } from '@/pages/publicSite/utils'
import { cardElevationStyle } from '@/pages/publicSite/components'
import { PUBLIC_SITE_STYLES } from '@/pages/publicSite/styles'
import { referralLink } from '@/lib/referral'
import { chatPalette } from '@/lib/chatLook'
import { detectNotifyState, enablePush, type NotifyState } from '@/lib/webPushClient'

// Portal del cliente (/c/:token) y página de una promo (/c/:token/promo/:promoId).
// Abre directo en el chat a pantalla completa, como una conversación de
// WhatsApp (pedido del dueño 2026-10-05: "debe ser una app parecida a
// WhatsApp, todo unificado"); citas, pedidos, tarjeta y promos viven en la
// info del negocio (ⓘ), igual que el perfil de un contacto.
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
  greeting: string
  quick_asks?: { icon: string; text: string; action?: string }[] | null
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
  has_audio?: boolean
}

interface PromoDetail {
  id: string
  title: string
  text: string
  image_url: string
  audio_url?: string
  coupon: PortalCoupon | null
}

interface PortalPush {
  available: boolean
  public_key: string
  subscribed_devices: number
}

interface PortalLoyalty {
  stamps: number
  required: number
  reward: string
  rewards_ready: number
  history: { label: string; at: string | null }[]
}

interface PortalData {
  account_available: boolean
  loyalty: PortalLoyalty | null
  push: PortalPush
  business: Business
  customer: { first_name: string }
  promotions: PromoSummary[]
  upcoming_appointments: PortalAppointment[]
  past_appointments: PortalAppointment[]
  orders: PortalOrder[]
  coupons: PortalCoupon[]
  /** Su código para recomendar el negocio ("" sin tarjeta de lealtad). */
  referral_code?: string
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
  const navigate = useNavigate()
  const isDesktop = useIsDesktop()
  const [chatPrefill, setChatPrefill] = useState<string | null>(null)
  // Una promo abre su página; todo lo demás, el chat.
  const [view, setView] = useState<'chat' | 'info'>(promoId ? 'info' : 'chat')
  useEffect(() => {
    setView(promoId ? 'info' : 'chat')
  }, [promoId, token])
  const chatOpen = view === 'chat'
  const setChatOpen = (open: boolean) => setView(open ? 'chat' : 'info')
  // Para el globito de "no leído" en la lista de chats de /mi.
  useEffect(() => {
    if (token && chatOpen) markChatSeen(token)
    return () => {
      if (token && chatOpen) markChatSeen(token)
    }
  }, [token, chatOpen])

  const { data, isLoading, isError } = useQuery<PortalData>({
    queryKey: ['portal', token],
    queryFn: () => api.get(`/public/portal/${token}`).then((r) => r.data),
    enabled: !!token,
    retry: false,
  })
  useNativeViewport(data ? getSiteTheme(data.business.site_theme).bg : undefined)

  // Para la lista de chats de /mi en este celular (aunque no haya entrado con su número).
  useEffect(() => {
    if (data && token)
      rememberChat({ portal_path: `/c/${token}`, name: data.business.name, logo_url: data.business.logo_url, color: data.business.color })
  }, [data, token])

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
    // ?chat=1: tocó el aviso de una respuesta del dueño — abrir el chat, donde está.
    const chat = params.get('chat')
    if (!n && !chat) return
    if (n) api.post(`/public/portal/${token}/opened`, { message_id: n }).catch(() => {})
    if (chat) setChatOpen(true)
    params.delete('n')
    params.delete('chat')
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
  // La info usa los colores del chat (lib/chatLook): fondo y paneles como WhatsApp.
  const pal = chatPalette(color, dark)
  const infoTheme: SiteThemeDef = { ...theme, bg: pal.bar, cardBg: pal.incoming, cardBorder: 'transparent', text: pal.text, muted: pal.meta }

  if (chatOpen) {
    // Atrás: a la lista de chats (/mi), como en WhatsApp — con su número, todos
    // sus negocios; si llegó por el link de WhatsApp, los chats de este celular.
    const back = () => navigate('/mi')
    const chat = (
      <AgentChat
        layout={isDesktop ? 'pane' : 'screen'}
        voiceBase={`/public/portal/${token}`}
        portalToken={token!}
        promoId={promoId}
        business={data.business}
        customerName={data.customer.first_name}
        theme={theme}
        prefill={chatPrefill}
        onClose={back}
        onInfo={() => setView('info')}
        banner={<ChatStrip data={data} theme={theme} onOpen={() => setView('info')} />}
      />
    )
    return (
      <>
        <SEO title={data.business.name} noIndex />
        <style>{PUBLIC_SITE_STYLES}</style>
        {/* En computadora, como WhatsApp Web: la lista de chats a la izquierda. */}
        {isDesktop ? <CustomerDesktopShell activePath={`/c/${token}`} current={data.business}>{chat}</CustomerDesktopShell> : chat}
      </>
    )
  }

  const info = (
    <div className="min-h-screen font-sans pb-12" style={{ background: infoTheme.bg, color: infoTheme.text }}>
      <div
        className="sticky top-0 z-20 flex items-center gap-3 px-2 py-2 shadow-sm"
        style={{ background: color, color: pal.onBrand, paddingTop: 'max(0.5rem, env(safe-area-inset-top, 0px))' }}
      >
        <button onClick={() => setView('chat')} aria-label="Volver al chat" className="press rounded-full p-2">
          <ArrowLeft size={22} />
        </button>
        <p className="text-[17px] font-semibold">{promoId ? 'Promoción' : 'Info. del negocio'}</p>
      </div>
      <div className="mx-auto max-w-lg px-3">
        <InfoProfile
          business={data.business}
          theme={infoTheme}
          onChat={openChat}
          catalogHref={data.business.slug ? `/sitio/${data.business.slug}` : null}
        />
        {promoId ? (
          <PromoView token={token!} promoId={promoId} business={data.business} theme={infoTheme} onWant={openChat} />
        ) : (
          <PortalHome token={token!} data={data} theme={infoTheme} onChat={openChat} />
        )}
        <p className="mt-10 text-center text-xs" style={{ color: theme.muted }}>
          Hecho con <span className="font-semibold">IaRadio</span>
          {data.account_available && (
            <>
              {' · '}
              <Link to="/mi" className="underline">
                Todos tus negocios en un lugar
              </Link>
            </>
          )}
        </p>
      </div>

    </div>
  )

  return (
    <>
      <SEO title={`Tu espacio en ${data.business.name}`} noIndex />
      <style>{PUBLIC_SITE_STYLES}</style>
      {/* "Info. del negocio", como la info de un contacto en WhatsApp: mismos
          colores que el chat, y lo que se pide aquí lo atiende el bot en el chat. */}
      {isDesktop ? (
        <CustomerDesktopShell activePath={`/c/${token}`} current={data.business}>
          <div className="absolute inset-0 overflow-y-auto">{info}</div>
        </CustomerDesktopShell>
      ) : (
        info
      )}
    </>
  )
}

// La franja fija arriba del chat: lo importante de un vistazo (sellos,
// próxima cita, cupones, avisos). Al tocarla se abre la info completa.
function ChatStrip({ data, theme, onOpen }: { data: PortalData; theme: SiteThemeDef; onOpen: () => void }) {
  const chips: string[] = []
  if (data.loyalty)
    chips.push(
      data.loyalty.rewards_ready > 0 ? '🎁 ¡Premio listo!' : `🎟️ ${data.loyalty.stamps}/${data.loyalty.required} sellos`
    )
  const next = data.upcoming_appointments[0]
  if (next) chips.push(`📅 ${fmtShort(next.scheduled_at)} ${fmtTime(next.scheduled_at)}`)
  if (data.coupons.length) chips.push(`🎫 ${data.coupons.length} ${data.coupons.length === 1 ? 'cupón' : 'cupones'}`)
  if (data.promotions.length) chips.push(`📣 ${data.promotions.length} ${data.promotions.length === 1 ? 'promo' : 'promos'}`)
  if (data.push.available && data.push.subscribed_devices === 0) chips.push('🔔 Activa avisos')
  if (!chips.length) return null
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex shrink-0 gap-2 overflow-x-auto px-3 py-2 text-left"
      style={{ borderBottom: `1px solid ${theme.cardBorder}` }}
    >
      {chips.map((c) => (
        <span
          key={c}
          className="shrink-0 whitespace-nowrap rounded-full px-3 py-1 text-xs font-medium"
          style={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}` }}
        >
          {c}
        </span>
      ))}
    </button>
  )
}

// Arriba de la info: foto grande, nombre y acciones redondas (como WhatsApp).
// Agendar y Pedir abren el chat: ahí lo atiende el bot.
function InfoProfile({
  business,
  theme,
  onChat,
  catalogHref,
}: {
  business: Business
  theme: SiteThemeDef
  onChat: (prefill?: string) => void
  catalogHref: string | null
}) {
  const color = business.color
  const actions: { label: string; icon: React.ReactNode; onClick?: () => void; href?: string }[] = [
    { label: 'Chat', icon: <MessageCircle size={22} />, onClick: () => onChat() },
    { label: 'Agendar', icon: <CalendarDays size={22} />, onClick: () => onChat('Quiero agendar una cita') },
    { label: 'Pedir', icon: <ShoppingBag size={22} />, onClick: () => onChat('Quiero hacer un pedido') },
    ...(catalogHref ? [{ label: 'Página', icon: <Store size={22} />, href: catalogHref }] : []),
  ]
  return (
    <section className="mt-3 rounded-xl px-4 pb-5 pt-6 text-center" style={{ background: theme.cardBg }}>
      {business.logo_url ? (
        <img src={business.logo_url} alt="" className="mx-auto h-24 w-24 rounded-full object-cover" />
      ) : (
        <div
          className="mx-auto flex h-24 w-24 items-center justify-center rounded-full text-4xl font-bold text-white"
          style={{ background: `linear-gradient(135deg, ${color}, ${color}99)` }}
        >
          {(business.name || '?')[0].toUpperCase()}
        </div>
      )}
      <h1 className="mt-3 text-2xl font-semibold">{business.name}</h1>
      {business.city && <p className="mt-0.5 text-sm" style={{ color: theme.muted }}>{business.city}</p>}
      <div className="mt-5 flex justify-center gap-3">
        {actions.map((a) => {
          const inner = (
            <>
              <span className="flex h-12 w-12 items-center justify-center rounded-full" style={{ color, border: `1px solid ${color}55` }}>
                {a.icon}
              </span>
              <span className="mt-1 block text-xs font-medium" style={{ color }}>{a.label}</span>
            </>
          )
          return a.href ? (
            <Link key={a.label} to={a.href} className="press w-16">{inner}</Link>
          ) : (
            <button key={a.label} type="button" onClick={a.onClick} className="press w-16">{inner}</button>
          )
        })}
      </div>
    </section>
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

      {data.loyalty && (
        <LoyaltyCardView loyalty={data.loyalty} color={color} business={business.name} storageKey={`stamps-seen:${token}`} />
      )}

      {data.loyalty && data.referral_code && business.slug && (
        <ReferralCard theme={theme} color={color} business={business.name} slug={business.slug} code={data.referral_code} />
      )}


      {data.push.available && (
        <NotifyCard
          token={token}
          push={data.push}
          theme={theme}
          color={color}
          hasUpcoming={data.upcoming_appointments.length > 0}
          stampGift={!!data.loyalty && !data.loyalty.history.some((h) => h.label === 'Activaste los avisos')}
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
                      <p className="font-semibold">
                        {p.has_audio && <span aria-label="Con audio">🔊 </span>}
                        {p.title}
                      </p>
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

// Recomiéndalo a un amigo: comparte su link personal; si el amigo se registra
// con él, el cliente gana un sello (backend: referral_service.py).
function ReferralCard({
  theme,
  color,
  business,
  slug,
  code,
}: {
  theme: SiteThemeDef
  color: string
  business: string
  slug: string
  code: string
}) {
  const [copied, setCopied] = useState(false)
  const share = async () => {
    const url = referralLink(slug, code)
    const text = `Te recomiendo ${business} 👌 Mira:`
    if (navigator.share) {
      try {
        await navigator.share({ title: business, text, url })
        return
      } catch {
        // canceló el menú de compartir: se copia
      }
    }
    try {
      await navigator.clipboard.writeText(`${text} ${url}`)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch {
      // sin portapapeles: nada que hacer
    }
  }
  return (
    <section
      className="mt-4 flex items-center gap-3 rounded-2xl p-4"
      style={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, ...cardElevationStyle(theme) }}
    >
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-xl" style={{ background: `${color}1f` }}>
        🤝
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold" style={{ color: theme.text }}>Recomienda a {business} y gana un sello</p>
        <p className="text-xs" style={{ color: theme.muted }}>Cuando un amigo se registre con tu link, te llega un sello.</p>
      </div>
      <button
        type="button"
        onClick={() => void share()}
        className="press shrink-0 rounded-full px-4 py-2 text-sm font-semibold text-white"
        style={{ background: color }}
      >
        {copied ? '¡Copiado!' : 'Compartir'}
      </button>
    </section>
  )
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

// "¿Te aviso?" — avisos gratis (Web Push) en vez de WhatsApp cobrado. El
// mejor momento para pedirlo es con una cita en puerta: el recordatorio de
// mañana es la razón concreta para aceptar.
function NotifyCard({
  token,
  push,
  theme,
  color,
  hasUpcoming,
  stampGift,
}: {
  token: string
  push: PortalPush
  theme: SiteThemeDef
  color: string
  hasUpcoming: boolean
  stampGift: boolean
}) {
  const qc = useQueryClient()
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
      const out = await enablePush(token, push.public_key)
      setState(out.state)
      // El sello de regalo por activar los avisos: que aparezca ya en la tarjeta.
      if (out.stamped) qc.invalidateQueries({ queryKey: ['portal', token] })
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

  const pitch = stampGift
    ? 'Activa los avisos y gana otro sello de regalo 🎁'
    : hasUpcoming
      ? '¿Te aviso un día antes de tu cita?'
      : '¿Te aviso de promociones y cupones?'

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

function LoyaltyCardView({
  loyalty,
  color,
  business,
  storageKey,
}: {
  loyalty: PortalLoyalty
  color: string
  business: string
  storageKey: string
}) {
  // Los sellos que el cliente todavía no había visto entran con animación (uno
  // tras otro) — es un momento de celebración, pasa pocas veces. La cuenta de
  // lo ya visto vive en este navegador; sin ella, se anima todo una vez.
  const [seenBefore] = useState<number | null>(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      return raw === null ? null : Number(raw)
    } catch {
      return null
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, String(loyalty.stamps))
    } catch {
      // almacenamiento bloqueado: solo se pierde la animación
    }
  }, [storageKey, loyalty.stamps])
  const animateFrom = seenBefore ?? 0
  const full = loyalty.rewards_ready > 0
  const missing = loyalty.required - loyalty.stamps
  // Recién llegó: solo tiene el sello de bienvenida — que se sienta el regalo.
  const justWelcomed = loyalty.stamps === 1 && loyalty.history[0]?.label === 'Regalo de bienvenida'

  return (
    <div
      className="mt-6 rounded-2xl p-5 text-white shadow-lg"
      style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)`, boxShadow: `0 12px 30px ${color}40` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider opacity-80">Tu tarjeta de cliente</p>
          <p className={`mt-1 font-bold leading-snug ${loyalty.reward.length > 40 ? 'text-base' : 'text-lg'}`}>{loyalty.reward}</p>
        </div>
        <Stamp size={22} className="shrink-0 opacity-80" />
      </div>

      <div className="mt-4 grid grid-cols-5 gap-2.5">
        {Array.from({ length: loyalty.required }, (_, i) => {
          const filled = full || i < loyalty.stamps
          const isNew = filled && i >= animateFrom
          return (
            <div
              key={i}
              className={`aspect-square rounded-full flex items-center justify-center${isNew ? ' anim-stamp' : ''}`}
              style={
                filled
                  ? { background: '#fff', color, animationDelay: isNew ? `${120 + (i - animateFrom) * 70}ms` : undefined }
                  : { border: '2px dashed rgba(255,255,255,0.55)', color: 'rgba(255,255,255,0.7)' }
              }
            >
              {filled ? <Check size={18} strokeWidth={3} /> : <span className="text-xs font-semibold">{i + 1}</span>}
            </div>
          )
        })}
      </div>

      <p className="mt-4 text-sm font-medium">
        {full
          ? `🎁 ¡Llenaste tu tarjeta! Pide tu premio en ${business}.`
          : justWelcomed
            ? `🎁 ¡Tu regalo de bienvenida! Ya tienes tu primer sello. Te faltan ${missing}.`
            : `Te faltan ${missing} ${missing === 1 ? 'sello' : 'sellos'} para tu premio.`}
      </p>
      <p className="mt-1 text-xs opacity-80">Ganas un sello con cada cita o pedido.</p>
    </div>
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
            {/* Campaña de radio: le llegó por la web en vez de nota de voz por WhatsApp. */}
            {promo.audio_url && (
              <div className="rounded-2xl p-3" style={{ background: `${color}14`, border: `1px solid ${color}33` }}>
                <p className="mb-2 text-sm font-semibold" style={{ color }}>
                  🔊 Escúchala
                </p>
                <audio controls preload="none" src={promo.audio_url} className="w-full">
                  Tu navegador no puede reproducir el audio.
                </audio>
              </div>
            )}
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
