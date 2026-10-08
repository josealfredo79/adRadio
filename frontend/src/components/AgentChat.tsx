import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import type { FaceMood } from '@/components/BotFace'
import MascotSmart from '@/components/MascotSmart'
import api from '@/lib/api'
import { ArrowLeft, CheckCheck, ClipboardList, Info, Mic, Send, ShoppingBag, Square, Volume2, VolumeX, X } from 'lucide-react'
import { isDarkTheme, type SiteThemeDef } from '@/pages/publicSite/theme'
import BubbleTail from '@/components/BubbleTail'
import InlineJoin from '@/components/InlineJoin'
import ChatNotifyOffer from '@/components/ChatNotifyOffer'
import OnboardingFlow from '@/components/OnboardingFlow'
import { parseChatOptions } from '@/lib/chatOptions'
import { speakable } from '@/lib/speakable'
import { chatPalette, dayLabel, hhmm, wallpaperPattern } from '@/lib/chatLook'
import { useSpeaker } from '@/lib/useSpeaker'
import { canRecordVoice, startVoiceRecording, type VoiceSession } from '@/lib/voiceRecorder'

// El chat con el agente (texto o voz, con la mascota 3D que habla). Lo usan
// el portal del cliente (/c/:token, con su historial) y la página pública del
// negocio (/sitio/:slug, visitante anónimo). Todo por la web: gratis, sin WhatsApp.

// La mascota que habla solo se descarga si el cliente usa la voz.
const Mascot3D = lazy(() => import('@/components/Mascot3D'))

export interface ChatBusiness {
  advertiser_id: string
  name: string
  agent: string
  color: string
  greeting: string
  // Botones de arranque propios del negocio (ej. la cuenta de ventas de
  // IaRadio); si no vienen, van los de siempre (QUICK_ASKS).
  quick_asks?: { icon: string; text: string; action?: string }[] | null
}

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
  // El bot pidió sus datos para pedir/agendar: debajo va el botón para registrarse.
  needsContact?: boolean
  // El agente propuso algo (cita, pedido…) y espera el "sí": botones Sí / No.
  confirm?: boolean
  // Lo contestó el dueño en persona (desde su Inbox), no el bot.
  fromOwner?: boolean
  // Aviso del sistema, no un mensaje (ej. "le llegó al negocio").
  note?: boolean
  // Cuándo (ISO): la hora en la burbuja y las etiquetas "Hoy" / "Ayer".
  at?: string
  // Botones del servidor para el paso actual (ej. qué día de la cita).
  quickReplies?: { label: string; value: string }[]
}

interface HistoryMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  channel: string
  from_owner: boolean
  at: string | null
}

// Cada cuánto el chat abierto revisa si el dueño ya contestó.
const OWNER_REPLY_POLL_MS = 8000
// Si la última plática fue hace más de esto, el bot vuelve a saludar.
const GREET_AGAIN_AFTER_MS = 60 * 60 * 1000
const DEFAULT_GREETING = '¡Hola! ¿En qué puedo ayudarte?'

// El bot saluda primero, con su nombre y el del cliente — un chat que abre
// vacío se siente como formulario. Si el dueño escribió su propio saludo
// (Widget de chat), ese manda.
function chatGreeting(business: ChatBusiness, customerName: string, returning: boolean): string {
  if (returning)
    return `¡Qué gusto verte de nuevo${customerName ? `, ${customerName}` : ''}! ¿En qué te ayudo hoy?`
  const hi = customerName ? `¡Hola, ${customerName}! 👋` : '¡Hola! 👋'
  const custom = (business.greeting || '').trim()
  if (custom && custom !== DEFAULT_GREETING) return /^¡?\s*hola/i.test(custom) ? custom : `${hi} ${custom}`
  return `${hi} Soy ${business.agent}, de ${business.name}. ¿En qué te ayudo hoy?`
}

// Para arrancar con un toque (en el celular escribir cuesta más que en WhatsApp).
const QUICK_ASKS: { icon: string; text: string; action?: string }[] = [
  { icon: '🛍️', text: '¿Qué productos tienen?' },
  { icon: '🕒', text: '¿Cuál es su horario?' },
  { icon: '📅', text: 'Quiero agendar una cita' },
  { icon: '🛒', text: 'Quiero hacer un pedido' },
]

export default function AgentChat({
  business,
  theme,
  voiceBase,
  portalToken,
  promoId,
  customerName = '',
  joinPath,
  whatsappHref,
  prefill,
  onClose,
  mascot3d = true,
  onEvent,
  layout = 'sheet',
  onInfo,
  banner,
}: {
  business: ChatBusiness
  theme: SiteThemeDef
  // Dónde viven /listen y /speak: /public/portal/{token} o /public/site/{slug}.
  voiceBase: string
  // Con link del portal: sesión ligada al cliente, historial y respuestas del dueño.
  // Sin él (página pública): visitante anónimo.
  portalToken?: string
  promoId?: string
  customerName?: string
  // A dónde mandar a registrarse cuando el bot pide sus datos (/q/{slug}).
  joinPath?: string
  // Si no hay registro con código, para pedir/agendar se va a WhatsApp.
  whatsappHref?: string
  prefill: string | null
  // Prueba A/B de la página pública (lib/mascotAb.ts): la mascota del
  // encabezado en 3D o en imagen fija, y avisar lo que pasa en la plática.
  mascot3d?: boolean
  onEvent?: (event: 'message' | 'confirmed' | 'whatsapp') => void
  onClose: () => void
  // 'screen': el chat ES la pantalla, como una conversación de WhatsApp (app del
  // cliente /mi y su tarjeta /c/...): flecha atrás, ⓘ para la info del negocio
  // y una franja fija arriba (sellos, cita, cupón). 'sheet': hoja encima de la
  // página pública del negocio.
  // 'pane': el lado derecho de la vista de computadora (como WhatsApp Web), a
  // lo ancho de su panel; sin flecha atrás porque la lista de chats está a la izquierda.
  layout?: 'sheet' | 'screen' | 'pane'
  onInfo?: () => void
  banner?: React.ReactNode
}) {
  const pane = layout === 'pane'
  const screen = layout === 'screen' || pane
  const color = business.color
  // La sesión se pide al abrir el chat, pero el primer mensaje puede salir
  // antes de que llegue (con texto precargado, el cliente toca Enviar al
  // instante) — y sin esperarla, el mensaje caía en otra sesión sin el
  // contexto de la promo ni el vínculo con el cliente.
  const sessionRef = useRef<Promise<string | null> | null>(null)
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [input, setInput] = useState(prefill ?? '')
  const [sending, setSending] = useState(false)
  // Hasta que carga el historial no se sabe si saludar como nuevo o "de nuevo".
  const [historyLoaded, setHistoryLoaded] = useState(false)
  // Reacción breve de la mascota a lo que pasó: feliz si algo quedó
  // confirmado (✅), confundida si faltó algo o falló. Vuelve sola a lo normal.
  const [reaction, setReaction] = useState<FaceMood | null>(null)
  const reactionTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const react = (m: FaceMood, ms: number) => {
    if (reactionTimer.current) clearTimeout(reactionTimer.current)
    setReaction(m)
    reactionTimer.current = setTimeout(() => setReaction(null), ms)
  }
  useEffect(() => () => {
    if (reactionTimer.current) clearTimeout(reactionTimer.current)
  }, [])
  // Lo que ya estaba (historial) aparece de una vez; lo nuevo entra con animación.
  const [historyCount, setHistoryCount] = useState(0)
  const [sentHere, setSentHere] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  // "✨ Quiero probarlo gratis" (chat de ventas de IaRadio): el alta se hace
  // aquí mismo, sin mandarlo al bot (OnboardingFlow).
  const [onboarding, setOnboarding] = useState(false)
  const [onbMood, setOnbMood] = useState<FaceMood | null>(null)
  const quickAsks = business.quick_asks?.length ? business.quick_asks : QUICK_ASKS
  const runQuickAsk = (q: { text: string; action?: string }) => {
    if (q.action === 'onboard') {
      setSentHere(true)
      setOnboarding(true)
    } else void send(q.text)
  }
  const scrollToEnd = useCallback(() => {
    requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }))
  }, [])
  const inputRef = useRef<HTMLInputElement>(null)
  // Modo voz: el cliente habla en vez de escribir y el bot le contesta en voz
  // alta, con la mascota que mueve la boca (voz de robot). Se activa al tocar el micrófono.
  const [voiceMode, setVoiceMode] = useState(false)
  const [recording, setRecording] = useState(false)
  const recorder = useRef<VoiceSession | null>(null)
  const speaker = useSpeaker({ endpoint: `${voiceBase}/speak`, robot: true })
  const micAvailable = canRecordVoice()

  useEffect(() => {
    sessionRef.current = portalToken
      ? api
          // Desde una promo, el backend le deja al bot el contexto de esa promo y
          // del cupón del cliente, para que "¡La quiero!" no reciba un "¿en qué te ayudo?".
          .post(`/public/portal/${portalToken}/chat-session`, promoId ? { promo_id: promoId } : undefined)
          .then((r) => r.data.session_id as string)
          .catch(() => null)
      : Promise.resolve(null) // visitante: la sesión la crea el primer mensaje
    inputRef.current?.focus()
  }, [portalToken, promoId])

  useEffect(() => () => recorder.current?.cancel(), [])

  // La plática de siempre (WhatsApp y web) arriba, y mientras el chat está
  // abierto, las respuestas que el dueño mande desde su Inbox aparecen solas.
  const lastAtRef = useRef<string | null>(null)
  useEffect(() => {
    let alive = true
    if (!portalToken) {
      // Visitante de la página: sin historial, solo el saludo.
      const greeting = chatGreeting(business, customerName, false)
      // Sin repetirlo si el efecto corre dos veces (StrictMode en desarrollo).
      setTurns((t) => (t[0]?.content === greeting ? t : [{ role: 'assistant', content: greeting, at: new Date().toISOString() }, ...t]))
      setHistoryLoaded(true)
      return () => {
        alive = false
      }
    }
    const token = portalToken
    const track = (msgs: HistoryMessage[]) => {
      const last = msgs[msgs.length - 1]?.at
      if (last) lastAtRef.current = last
    }
    api
      .get(`/public/portal/${token}/messages`)
      .then((r) => {
        if (!alive) return
        const msgs: HistoryMessage[] = r.data.messages ?? []
        track(msgs)
        lastAtRef.current ??= new Date().toISOString()
        setHistoryCount(msgs.length)
        const last = msgs[msgs.length - 1]?.at
        const stale = !last || Date.now() - new Date(last).getTime() > GREET_AGAIN_AFTER_MS
        const greeting: ChatTurn[] = stale
          ? [{ role: 'assistant', content: chatGreeting(business, customerName, msgs.length > 0), at: new Date().toISOString() }]
          : []
        setTurns((t) => [
          ...msgs.map((m) => ({ role: m.role, content: m.content, fromOwner: m.from_owner, at: m.at ?? undefined })),
          ...greeting,
          ...t,
        ])
      })
      .catch(() => {
        if (alive) setTurns((t) => [{ role: 'assistant', content: chatGreeting(business, customerName, false) }, ...t])
      })
      .finally(() => {
        if (alive) setHistoryLoaded(true)
      })
    const timer = setInterval(() => {
      if (!lastAtRef.current) return
      api
        .get(`/public/portal/${token}/messages`, { params: { after: lastAtRef.current } })
        .then((r) => {
          if (!alive) return
          const msgs: HistoryMessage[] = r.data.messages ?? []
          track(msgs)
          // Lo demás (lo que escribió el cliente y lo que contestó el bot) ya está en pantalla.
          const owner = msgs.filter((m) => m.from_owner)
          if (owner.length)
            setTurns((t) => [...t, ...owner.map((m) => ({ role: 'assistant' as const, content: m.content, fromOwner: true, at: m.at ?? undefined }))])
        })
        .catch(() => {})
    }, OWNER_REPLY_POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
    // business y customerName solo cuentan al abrir: el saludo no cambia a media plática.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [portalToken])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns, sending])

  // Registro dentro del chat (InlineJoin): el slug sale de joinPath (/q/{slug}).
  const joinSlug = joinPath?.startsWith('/q/') ? joinPath.slice(3) : null
  const [joinedToken, setJoinedToken] = useState<string | null>(null)
  const lastNeedsContact = turns.reduce((acc, t, k) => (t.needsContact ? k : acc), -1)
  // Cliente identificado (se registró en el chat o entró por su portal) y una
  // cita recién confirmada: se le ofrecen los avisos ahí mismo.
  const knownToken = joinedToken ?? portalToken ?? null
  const bookedAt = turns.reduce(
    (acc, t, k) => (t.role === 'assistant' && /^✅\s*\*?¡?Cita confirmada/i.test(t.content.trim()) ? k : acc),
    -1
  )

  const onJoined = (token: string, firstName: string) => {
    setJoinedToken(token)
    // Desde aquí la plática ya es del cliente verificado (como en su portal).
    sessionRef.current = api
      .post(`/public/portal/${token}/chat-session`)
      .then((r) => r.data.session_id as string)
      .catch(() => null)
    // Abrir su tarjeta le da el sello de bienvenida.
    void api.get(`/public/portal/${token}`).catch(() => {})
    setTurns((t) => [
      ...t,
      {
        role: 'assistant',
        note: true,
        at: new Date().toISOString(),
        content: `¡Listo${firstName ? `, ${firstName}` : ''}! Ya eres cliente de ${business.name} 🎉`,
      },
    ])
    react('happy', 2500)
    // Lo que había pedido (la cita, el pedido) sigue solo, sin repetirlo.
    const asked = [...turns].slice(0, lastNeedsContact).reverse().find((t) => t.role === 'user')?.content
    if (asked) setTimeout(() => void send(asked, false, false), 300)
  }

  // echo=false: se manda sin volver a pintar la burbuja del cliente (al
  // retomar lo que pidió antes de registrarse).
  // shown: lo que se ve en la burbuja del cliente si es distinto de lo que se manda
  // (tocó el botón "9:30 am" → se manda "2", se ve "9:30 am").
  const send = async (text?: string, spoken = voiceMode, echo = true, shown?: string) => {
    const message = (text ?? input).trim()
    if (!message || sending) return
    if (text === undefined) setInput('')
    setSentHere(true)
    onEvent?.('message')
    if (echo) setTurns((t) => [...t, { role: 'user', content: shown ?? message, at: new Date().toISOString() }])
    setSending(true)
    try {
      const sessionId = await sessionRef.current
      // El agente puede pensar varias vueltas (tope de 25 s en el servidor): los 10 s
      // de siempre cortaban la respuesta y salía "no me llegó tu mensaje".
      const r = await api.post(`/widget/chat/${business.advertiser_id}`, { message, session_id: sessionId }, { timeout: 45000 })
      sessionRef.current = Promise.resolve(r.data.session_id)
      if (r.data.handoff) {
        // El dueño está atendiendo en persona: el bot no contesta, le avisa.
        setTurns((t) =>
          t[t.length - 2]?.note
            ? t
            : [...t, { role: 'assistant', note: true, at: new Date().toISOString(), content: `Tu mensaje le llegó a ${business.name}. Te contesta aquí mismo.` }]
        )
        return
      }
      const reply: string = r.data.reply
      setTurns((t) => {
        // Sin repetir una tarjeta que acaba de salir (ej. tocó "Lo quiero" en
        // ella y el bot habla del mismo producto).
        const recent = new Set(
          t.slice(-4).flatMap((turn) => (turn.cards ?? []).map((c) => c.url))
        )
        const cards: ProductCard[] = (r.data.cards ?? []).filter((c: ProductCard) => !recent.has(c.url))
        return [
          ...t,
          {
            role: 'assistant',
            content: reply,
            at: new Date().toISOString(),
            cards,
            quickReplies: r.data.quick_replies ?? [],
            needsContact: !!r.data.needs_contact,
            confirm: !!r.data.confirm,
          },
        ]
      })
      if (reply.trimStart().startsWith('✅')) {
        react('happy', 2500)
        onEvent?.('confirmed')
      }
      else if (r.data.needs_contact) react('confused', 1800)
      if (spoken) void speaker.speak(speakable(reply))
    } catch {
      react('confused', 1800)
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
      const r = await api.post(`${voiceBase}/listen`, form)
      setSending(false)
      await send(r.data.transcript, true)
    } catch {
      setSending(false)
      setTurns((t) => [...t, { role: 'assistant', content: 'No alcancé a escucharte. ¿Me lo repites o me lo escribes?' }])
    }
  }

  const mood: FaceMood = recording
    ? 'listening'
    : sending
      ? 'thinking'
      : speaker.speaking
        ? 'speaking'
        : (reaction ?? 'idle')

  const pal = chatPalette(color, isDarkTheme(theme))

  return (
    <div
      className={pane ? 'absolute inset-0 flex' : screen ? 'fixed inset-0 z-30 flex justify-center' : 'fixed inset-0 z-30 flex items-end justify-center sm:items-center'}
      style={screen ? { background: pal.wallpaper } : undefined}
      onClick={screen ? undefined : onClose}
    >
      {/* El fondo se oscurece aparte: si la hoja viviera dentro del mismo
          desvanecido, se vería transparente mientras sube. */}
      {!screen && <div className="anim-backdrop absolute inset-0 bg-black/50" aria-hidden />}
      <div
        className={
          pane
            ? 'relative flex h-full w-full flex-col overflow-hidden'
            : screen
            ? 'relative flex h-[100dvh] w-full max-w-lg flex-col overflow-hidden'
            : 'anim-sheet h-sheet relative flex w-full max-w-lg flex-col overflow-hidden rounded-t-3xl sm:rounded-3xl'
        }
        style={{ background: pal.wallpaper, color: pal.text }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Encabezado como el de WhatsApp, en el color del negocio. */}
        <div
          className={`flex items-center justify-between ${screen ? 'px-1.5' : 'px-3'} py-2 shadow-sm`}
          style={{
            background: color,
            color: pal.onBrand,
            paddingTop: screen ? 'max(0.5rem, env(safe-area-inset-top, 0px))' : undefined,
          }}
        >
          <div className="flex min-w-0 items-center gap-1.5">
            {screen && !pane && (
              <button onClick={onClose} aria-label="Atrás" className="press shrink-0 rounded-full p-1.5">
                <ArrowLeft size={22} />
              </button>
            )}
            {/* La mascota es la foto de perfil: piensa mientras busca, se alegra al confirmar.
                En modo voz sale grande abajo, así que aquí se quita. */}
            {!voiceMode && (
              <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white/95">
                <MascotSmart mood={mood} size={40} color={color} allow3d={mascot3d || onboarding} />
              </div>
            )}
            <button
              type="button"
              onClick={screen ? onInfo : undefined}
              disabled={!screen || !onInfo}
              className="min-w-0 pl-1 text-left"
            >
              <p className="truncate text-[16px] font-semibold leading-tight">{screen ? business.name : business.agent}</p>
              <p className="truncate text-xs leading-tight opacity-80">
                {sending ? 'escribiendo…' : screen ? `${business.agent} · en línea` : `${business.name} · en línea`}
              </p>
            </button>
          </div>
          <div className="flex items-center">
            {voiceMode && (
              <button
                onClick={() => speaker.setMuted(!speaker.muted)}
                aria-label={speaker.muted ? 'Activar la voz' : 'Silenciar la voz'}
                className="rounded-full p-2 opacity-90"
              >
                {speaker.muted ? <VolumeX size={20} /> : <Volume2 size={20} />}
              </button>
            )}
            {screen ? (
              onInfo && (
                <button onClick={onInfo} aria-label={`Info de ${business.name}`} className="press rounded-full p-2 opacity-90">
                  <Info size={22} />
                </button>
              )
            ) : (
              <button onClick={onClose} aria-label="Cerrar chat" className="rounded-full p-2 opacity-90">
                <X size={20} />
              </button>
            )}
          </div>
        </div>

        {banner}

        {(voiceMode || (onboarding && onbMood)) && (
          <div
            className="flex shrink-0 flex-col items-center pt-1 pb-1"
            style={{ background: `color-mix(in srgb, ${color} 22%, #0a0f2e)` }}
          >
            <Suspense fallback={<div style={{ height: 150 }} />}>
              <Mascot3D mood={onboarding && onbMood ? onbMood : mood} getLevel={speaker.level} size={130} color={color} />
            </Suspense>
          </div>
        )}

        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto overscroll-contain px-3 py-3"
          style={{ backgroundImage: wallpaperPattern(pal.doodle), backgroundSize: '160px 160px' }}
        >
          {/* El toque IaRadio: como el aviso amarillo de WhatsApp, pero diciendo lo que vale este chat. */}
          <p
            className="mx-auto mb-3 max-w-[88%] rounded-lg px-3 py-1.5 text-center text-[12.5px] leading-snug shadow-sm"
            style={{ background: pal.notice, color: pal.noticeText }}
          >
            {/* En el chat de ventas de IaRadio (el que trae el botón del alta) el aviso
                dice lo que se puede hacer ahí, no "Chat de IaRadio con IaRadio". */}
            {quickAsks.some((q) => q.action === 'onboard')
              ? '📻 Pregúntame lo que quieras de IaRadio o arma tu página gratis aquí mismo, en 5 minutos.'
              : `📻 Chat de ${business.name} con IaRadio: te contestan al instante y no gasta tus datos de WhatsApp.`}
          </p>
          {turns.map((t, i) => {
            const prev = turns[i - 1]
            const day = t.at ? dayLabel(t.at) : null
            const prevDay = prev?.at ? dayLabel(prev.at) : null
            const showDay = !!day && day !== prevDay
            const firstOfGroup = showDay || !prev || prev.role !== t.role || !!prev.note || prev.fromOwner !== t.fromOwner
            // Opciones numeradas (horarios…): en la web nunca se ven las instrucciones de
            // WhatsApp ("responde con el número"); los botones solo en el último mensaje.
            const parsed = t.role === 'assistant' && !t.note ? parseChatOptions(t.content) : null
            const choices = parsed && i === turns.length - 1 ? parsed : null
            const mine = t.role === 'user'
            return (
              <div key={i} className={i >= historyCount ? 'anim-bubble' : undefined}>
                {showDay && (
                  <p
                    className="mx-auto my-3 w-fit rounded-lg px-3 py-1 text-xs font-medium shadow-sm"
                    style={{ background: pal.incoming, color: pal.meta }}
                  >
                    {day}
                  </p>
                )}
                {t.note ? (
                  <p
                    className="mx-auto my-2 w-fit max-w-[85%] rounded-lg px-3 py-1 text-center text-xs shadow-sm"
                    style={{ background: pal.notice, color: pal.noticeText }}
                  >
                    {t.content}
                  </p>
                ) : (
                  <div className={firstOfGroup ? 'mt-2.5' : 'mt-0.5'}>
                    <div className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
                      <div
                        className="relative max-w-[82%] rounded-lg px-2.5 pb-1.5 pt-1.5 text-[15px] leading-snug shadow-sm"
                        style={{
                          background: mine ? pal.outgoing : pal.incoming,
                          color: pal.text,
                          ...(firstOfGroup ? (mine ? { borderTopRightRadius: 0 } : { borderTopLeftRadius: 0 }) : {}),
                        }}
                      >
                        {firstOfGroup && <BubbleTail side={mine ? 'right' : 'left'} fill={mine ? pal.outgoing : pal.incoming} />}
                        {t.fromOwner && firstOfGroup && (
                          <p className="mb-0.5 text-[13px] font-semibold" style={{ color: pal.accent }}>
                            {business.name} en persona
                          </p>
                        )}
                        <span className="whitespace-pre-line break-words">
                          {renderChatText(parsed ? parsed.text || 'Elige una opción:' : t.content)}
                        </span>
                        {/* Hora y palomitas abajo a la derecha, como en WhatsApp. */}
                        <span className="float-right ml-2 mt-1.5 flex translate-y-0.5 items-center gap-0.5 text-[11px] leading-none" style={{ color: pal.meta }}>
                          {t.at ? hhmm(t.at) : ''}
                          {mine && <CheckCheck size={15} style={{ color: pal.ticks }} aria-label="Entregado" />}
                        </span>
                      </div>
                    </div>
                    {/* Botones que manda el servidor (días de la cita, el nombre): solo en el último mensaje. */}
                    {!choices && i === turns.length - 1 && !!t.quickReplies?.length && (
                      <div className="mt-1.5 flex max-w-[82%] flex-wrap gap-2">
                        {t.quickReplies.map((q) => (
                          <button
                            key={q.value}
                            type="button"
                            onClick={() => void send(q.value, false, true, q.label)}
                            disabled={sending}
                            className="press min-w-[5.5rem] rounded-xl px-4 py-2.5 text-[15px] font-semibold shadow-sm disabled:opacity-50"
                            style={{ background: pal.incoming, color: pal.accent }}
                          >
                            {q.label}
                          </button>
                        ))}
                      </div>
                    )}
                    {/* Opciones numeradas del bot (horarios…) como botones: solo en el último mensaje. */}
                    {choices && (
                      <div className="mt-1.5 flex max-w-[82%] flex-wrap gap-2">
                        {choices.options.map((o) => (
                          <button
                            key={o.n}
                            type="button"
                            onClick={() => void send(o.n, false, true, o.label)}
                            disabled={sending}
                            className="press min-w-[5.5rem] rounded-xl px-4 py-2.5 text-[15px] font-semibold shadow-sm disabled:opacity-50"
                            style={{ background: pal.incoming, color: pal.accent }}
                          >
                            {o.label}
                          </button>
                        ))}
                        {choices.more && (
                          <button
                            type="button"
                            onClick={() => void send('MAS', false, true, 'Ver más horarios')}
                            disabled={sending}
                            className="press min-w-[5.5rem] rounded-xl px-4 py-2.5 text-[15px] font-semibold shadow-sm disabled:opacity-50"
                            style={{ background: color, color: pal.onBrand }}
                          >
                            Ver más horarios
                          </button>
                        )}
                      </div>
                    )}
                    {t.confirm && i === turns.length - 1 && !sending && (
                      <div className="mt-1.5 flex gap-2">
                        <button
                          onClick={() => void send('Sí, confírmalo')}
                          className="press rounded-full px-4 py-2 text-sm font-semibold shadow-sm"
                          style={{ background: color, color: pal.onBrand }}
                        >
                          Sí, confírmalo
                        </button>
                        <button
                          onClick={() => void send('No, gracias')}
                          className="press rounded-full px-4 py-2 text-sm font-semibold shadow-sm"
                          style={{ background: pal.incoming, color: pal.text }}
                        >
                          No
                        </button>
                      </div>
                    )}
                    {t.needsContact && joinSlug && i === lastNeedsContact && !joinedToken && (
                      <InlineJoin slug={joinSlug} color={color} onBrand={pal.onBrand} pal={pal} onVerified={onJoined} />
                    )}
                    {t.needsContact && !joinSlug && whatsappHref && (
                      <a
                        href={whatsappHref}
                        target="_blank"
                        onClick={() => onEvent?.('whatsapp')}
                        rel="noreferrer"
                        className="mt-1.5 inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold shadow-sm"
                        style={{ background: color, color: pal.onBrand }}
                      >
                        <ClipboardList size={16} /> Seguir por WhatsApp
                      </a>
                    )}
                    {/* Productos que mencionó el bot: foto, precio y "Lo quiero" */}
                    {t.cards && t.cards.length > 0 && (
                      <div className="mt-1.5 flex gap-2 overflow-x-auto pb-1">
                        {t.cards.map((c) => (
                          <div key={c.url} className="w-36 shrink-0 overflow-hidden rounded-lg shadow-sm" style={{ background: pal.incoming }}>
                            <a href={c.url} target="_blank" rel="noopener noreferrer">
                              {c.photo_url ? (
                                <img src={c.photo_url} alt={c.name} className="h-24 w-full object-cover" loading="lazy" />
                              ) : (
                                <div className="flex h-24 items-center justify-center" style={{ color: pal.meta }}>
                                  <ShoppingBag size={28} />
                                </div>
                              )}
                            </a>
                            <div className="p-2.5">
                              <p className="line-clamp-2 text-sm font-semibold leading-snug">{c.name}</p>
                              {c.price && <p className="text-sm" style={{ color: pal.meta }}>{c.price}</p>}
                              <button
                                onClick={() => void send(`Quiero ${c.name}`)}
                                disabled={sending}
                                className="mt-2 w-full rounded-full py-1.5 text-sm font-semibold disabled:opacity-50"
                                style={{ background: color, color: pal.onBrand }}
                              >
                                Lo quiero
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
          {onboarding && (
            <OnboardingFlow pal={pal} brand={color} onBrand={pal.onBrand} onActivity={scrollToEnd} onExit={() => setOnboarding(false)} onVoiceMood={setOnbMood} />
          )}
          {knownToken && bookedAt >= historyCount && <ChatNotifyOffer token={knownToken} pal={pal} color={color} />}
          {historyLoaded && !sentHere && (
            <div className="mx-auto mt-4 w-full max-w-2xl text-center">
              <p className="mx-auto w-fit rounded-lg px-3 py-1 text-xs shadow-sm" style={{ background: pal.incoming, color: pal.meta }}>
                {micAvailable ? 'Escríbeme o toca el micrófono y háblame 🎙️' : 'Pregúntame precios, horarios, citas o pedidos'}
              </p>
              {/* En una fila, como accesos directos: ícono arriba y texto abajo (cabe en el celular). */}
              <div className="mt-3 grid grid-cols-4 gap-2">
                {quickAsks.map((q) => (
                  <button
                    key={q.text}
                    onClick={() => runQuickAsk(q)}
                    className="press flex flex-col items-center justify-start gap-1.5 rounded-xl px-1.5 py-3 text-center text-[13px] font-semibold leading-tight shadow-sm sm:text-[15px]"
                    style={{ background: pal.incoming, color: pal.accent }}
                  >
                    <span className="text-2xl" aria-hidden>{q.icon}</span>
                    <span>{q.text}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {sending && (
            <div className="mt-2.5 flex justify-start">
              <div
                className="relative flex items-center gap-1 rounded-lg px-3.5 py-3 shadow-sm"
                style={{ background: pal.incoming, borderTopLeftRadius: 0 }}
                aria-label={voiceMode ? 'Pensando…' : 'Escribiendo…'}
              >
                <BubbleTail side="left" fill={pal.incoming} />
                {[0, 1, 2].map((d) => (
                  <span
                    key={d}
                    className="typing-dot h-2 w-2 rounded-full"
                    style={{ background: pal.meta, animationDelay: `${d * 160}ms` }}
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Después del primer mensaje los accesos directos siguen a la mano (si
            escribió en vez de tocar, o salió del alta, no se pierden). */}
        {!onboarding && sentHere && (
          // Bajan a otra línea si no caben: deslizar de lado no se nota en la computadora.
          <div className="grid grid-cols-2 gap-1.5 px-2 pt-2 sm:flex sm:flex-wrap sm:justify-center" style={{ background: pal.bar }}>
            {quickAsks.map((q) => (
              <button
                key={q.text}
                type="button"
                onClick={() => runQuickAsk(q)}
                disabled={sending}
                className="press flex min-w-0 items-center justify-center gap-1 rounded-full border px-2.5 py-1.5 text-[12.5px] font-semibold leading-tight shadow-sm disabled:opacity-50"
                style={q.action === 'onboard'
                  ? { background: color, color: pal.onBrand, borderColor: color }
                  : { background: pal.incoming, color: pal.accent, borderColor: `color-mix(in srgb, ${pal.accent} 45%, transparent)` }}
              >
                <span aria-hidden>{q.icon}</span>
                {q.text}
              </button>
            ))}
          </div>
        )}
        {!onboarding && <form
          onSubmit={(e) => {
            e.preventDefault()
            void send(undefined, false)
          }}
          className="flex items-center gap-1.5 px-2 pt-2"
          style={{
            background: pal.bar,
            // Arriba de la barra de inicio del iPhone cuando está instalada como app.
            paddingBottom: 'calc(0.5rem + env(safe-area-inset-bottom, 0px))',
          }}
        >
          {recording ? (
            <p className="flex-1 rounded-full px-4 py-3 text-[15px]" style={{ background: pal.field, color: pal.meta }}>
              🔴 Te escucho… toca el cuadro al terminar
            </p>
          ) : (
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={500}
              placeholder="Mensaje"
              enterKeyHint="send"
              className="min-w-0 flex-1 rounded-full px-4 py-3 text-base outline-none"
              style={{ background: pal.field, color: pal.text }}
            />
          )}
          {micAvailable && !input.trim() ? (
            <button
              type="button"
              onClick={() => void (recording ? stopRecording() : startRecording())}
              disabled={sending}
              aria-label={recording ? 'Terminar de hablar' : 'Hablar'}
              className="press flex h-12 w-12 shrink-0 items-center justify-center rounded-full shadow-sm disabled:opacity-50"
              style={{ background: recording ? '#f43f5e' : color, color: recording ? '#fff' : pal.onBrand }}
            >
              {recording ? <Square size={16} fill="currentColor" /> : <Mic size={21} />}
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim() || sending}
              aria-label="Enviar"
              className="press flex h-12 w-12 shrink-0 items-center justify-center rounded-full shadow-sm disabled:opacity-50"
              style={{ background: color, color: pal.onBrand }}
            >
              <Send size={19} />
            </button>
          )}
        </form>}
      </div>
    </div>
  )
}
