import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import api from '@/lib/api'
import { ClipboardList, Mic, Send, ShoppingBag, Square, Volume2, VolumeX, X } from 'lucide-react'
import type { SiteThemeDef } from '@/pages/publicSite/theme'
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
  // Lo contestó el dueño en persona (desde su Inbox), no el bot.
  fromOwner?: boolean
  // Aviso del sistema, no un mensaje (ej. "le llegó al negocio").
  note?: boolean
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
const QUICK_ASKS = ['¿Qué productos tienen?', '¿Cuál es su horario?', 'Quiero agendar una cita', 'Quiero hacer un pedido']

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
  // Hasta que carga el historial no se sabe si saludar como nuevo o "de nuevo".
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [sentHere, setSentHere] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
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
      setTurns((t) => (t[0]?.content === greeting ? t : [{ role: 'assistant', content: greeting }, ...t]))
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
        const last = msgs[msgs.length - 1]?.at
        const stale = !last || Date.now() - new Date(last).getTime() > GREET_AGAIN_AFTER_MS
        const greeting: ChatTurn[] = stale
          ? [{ role: 'assistant', content: chatGreeting(business, customerName, msgs.length > 0) }]
          : []
        setTurns((t) => [
          ...msgs.map((m) => ({ role: m.role, content: m.content, fromOwner: m.from_owner })),
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
            setTurns((t) => [...t, ...owner.map((m) => ({ role: 'assistant' as const, content: m.content, fromOwner: true }))])
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

  const send = async (text?: string, spoken = voiceMode) => {
    const message = (text ?? input).trim()
    if (!message || sending) return
    if (text === undefined) setInput('')
    setSentHere(true)
    setTurns((t) => [...t, { role: 'user', content: message }])
    setSending(true)
    try {
      const sessionId = await sessionRef.current
      const r = await api.post(`/widget/chat/${business.advertiser_id}`, { message, session_id: sessionId })
      sessionRef.current = Promise.resolve(r.data.session_id)
      if (r.data.handoff) {
        // El dueño está atendiendo en persona: el bot no contesta, le avisa.
        setTurns((t) =>
          t[t.length - 2]?.note
            ? t
            : [...t, { role: 'assistant', note: true, content: `Tu mensaje le llegó a ${business.name}. Te contesta aquí mismo.` }]
        )
        return
      }
      const reply: string = r.data.reply
      setTurns((t) => [
        ...t,
        { role: 'assistant', content: reply, cards: r.data.cards ?? [], needsContact: !!r.data.needs_contact },
      ])
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
      const r = await api.post(`${voiceBase}/listen`, form)
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
          <div className="flex shrink-0 flex-col items-center bg-[#0a0f2e] pt-1 pb-1">
            <Suspense fallback={<div style={{ height: 150 }} />}>
              <Mascot3D mood={mood} getLevel={speaker.level} size={130} />
            </Suspense>
          </div>
        )}

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {turns.map((t, i) =>
            t.note ? (
              <p key={i} className="mx-auto max-w-[85%] text-center text-xs" style={{ color: theme.muted }}>
                {t.content}
              </p>
            ) : (
            <div key={i}>
              {t.fromOwner && (
                <p className="mb-1 text-xs font-semibold" style={{ color }}>
                  {business.name} te respondió
                </p>
              )}
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
              {t.needsContact && (joinPath || whatsappHref) && (
                <a
                  href={joinPath || whatsappHref}
                  target={joinPath ? undefined : '_blank'}
                  rel="noreferrer"
                  className="mt-2 inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold text-white"
                  style={{ background: color }}
                >
                  <ClipboardList size={16} /> {joinPath ? 'Dejar mis datos (te llega un código)' : 'Seguir por WhatsApp'}
                </a>
              )}
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
            )
          )}
          {historyLoaded && !sentHere && (
            <div className="mx-auto mt-2 max-w-sm text-center">
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
