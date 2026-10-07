import { useState, useEffect, useRef, useCallback } from 'react'
import { X, Send, CheckCheck } from 'lucide-react'
import MascotSmart from '@/components/MascotSmart'
import BubbleTail from '@/components/BubbleTail'
import { chatPalette, hhmm, wallpaperPattern } from '@/lib/chatLook'

interface ProductCard {
  url: string
  name: string
  price: string | null
  photo_url: string
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  cards?: ProductCard[]
  at?: string
}

const STORAGE_KEY = 'iaradio_demo_session'
// Los colores del chat de la app del cliente (verde IaRadio, fondo oscuro).
const GREEN = '#25D366'
const PAL = chatPalette(GREEN, true)
const BG = '#0b0d16'
const CARD = '#151926'
const BORDER = 'rgba(255,255,255,0.09)'
const API_BASE = `${import.meta.env.VITE_API_URL ?? ''}/api/v1`
const SITE_ORIGIN = typeof window !== 'undefined' ? window.location.origin : ''

function ProductCardPreview({ card }: { card: ProductCard }) {
  return (
    <a
      href={`${SITE_ORIGIN}${card.url}`}
      target="_blank"
      rel="noopener noreferrer"
      className="flex w-full items-center gap-2.5 rounded-2xl border border-white/10 bg-[#151926] p-2 transition-colors hover:border-[#25D366]"
    >
      <div className="h-11 w-11 shrink-0 rounded-md bg-gray-700 overflow-hidden flex items-center justify-center">
        {card.photo_url ? (
          <img src={card.photo_url} alt={card.name} className="h-full w-full object-cover" />
        ) : (
          <span className="text-lg">🎙️</span>
        )}
      </div>
      <div className="min-w-0">
        <div className="text-xs font-semibold text-white truncate">{card.name}</div>
        {card.price && <div className="text-xs text-white/60">{card.price}</div>}
      </div>
    </a>
  )
}

function getSessionId(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

function saveSessionId(id: string) {
  try {
    localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // localStorage no disponible (modo privado, cuota llena, etc.) — ignorar
  }
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(getSessionId)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([
        {
          role: 'assistant',
          at: new Date().toISOString(),
          content:
            '👋 ¡Hola! Soy Alex, el asistente de IaRadio.\n\n¿Te gustaría saber cómo podemos ayudarte a automatizar tus ventas por WhatsApp con IA?',
        },
      ])
    }
  }, [open, messages.length])

  useEffect(() => {
    // Solo la caja del chat, nunca la página (ver WhatsAppMockup).
    const box = endRef.current?.closest('.overflow-y-auto')
    box?.scrollTo({ top: box.scrollHeight, behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 300)
    }
  }, [open])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: text, at: new Date().toISOString() }])
    setLoading(true)

    let sid = sessionId
    if (!sid) {
      sid = crypto.randomUUID()
      setSessionId(sid)
      saveSessionId(sid)
    }

    try {
      const res = await fetch(`${API_BASE}/chat/demo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sid }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply, cards: data.cards, at: new Date().toISOString() }])
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          at: new Date().toISOString(),
          content: 'Lo siento, hubo un error al conectar. ¿Puedes intentar de nuevo? 🙏',
        },
      ])
    } finally {
      setLoading(false)
    }
  }, [input, loading, sessionId])

  // Mismo aspecto que el chat de la app del cliente (AgentChat): la mascota de
  // IaRadio como avatar y botón, globos tipo WhatsApp, caja redonda. Antes era
  // otro diseño (degradado morado, icono de robot) y parecían dos productos.
  return (
    <div className="fixed bottom-5 right-4 z-50 flex flex-col items-end sm:right-6">
      {open && (
        <div
          className="mb-3 flex h-[70dvh] max-h-[34rem] w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-3xl shadow-2xl sm:w-96"
          style={{ animation: 'fadeUp 0.3s ease', background: BG, color: '#fff', border: `1px solid ${BORDER}` }}
        >
          {/* Mismo encabezado que el chat de los negocios (AgentChat): estilo WhatsApp. */}
          <div className="flex items-center justify-between px-3 py-2 shadow-sm" style={{ background: GREEN, color: PAL.onBrand }}>
            <div className="flex min-w-0 items-center gap-2">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white/95">
                <MascotSmart mood={loading ? 'thinking' : 'idle'} size={40} color={GREEN} />
              </div>
              <div className="min-w-0">
                <p className="truncate text-[16px] font-semibold leading-tight">Alex · IaRadio</p>
                <p className="truncate text-xs leading-tight opacity-80">{loading ? 'escribiendo…' : 'en línea'}</p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Cerrar chat" className="rounded-full p-2 opacity-90">
              <X size={20} />
            </button>
          </div>

          <div
            className="custom-scrollbar flex-1 overflow-y-auto overscroll-contain px-3 py-3"
            style={{ background: PAL.wallpaper, backgroundImage: wallpaperPattern(PAL.doodle), backgroundSize: '160px 160px' }}
          >
            {messages.map((msg, i) => {
              const mine = msg.role === 'user'
              const first = i === 0 || messages[i - 1].role !== msg.role
              const fill = mine ? PAL.outgoing : PAL.incoming
              return (
                <div
                  key={i}
                  className={`flex ${mine ? 'justify-end' : 'justify-start'} ${first ? 'mt-2.5' : 'mt-0.5'}`}
                  style={{ animation: 'fadeUp 0.3s ease' }}
                >
                  <div className={`flex max-w-[85%] flex-col gap-1.5 ${mine ? 'items-end' : 'items-start'}`}>
                    <div
                      className="relative rounded-lg px-2.5 py-1.5 text-[15px] leading-snug shadow-sm"
                      style={{
                        background: fill,
                        color: PAL.text,
                        ...(first ? (mine ? { borderTopRightRadius: 0 } : { borderTopLeftRadius: 0 }) : {}),
                      }}
                    >
                      {first && <BubbleTail side={mine ? 'right' : 'left'} fill={fill} />}
                      <span className="whitespace-pre-line break-words">{msg.content}</span>
                      <span className="float-right ml-2 mt-1.5 flex translate-y-0.5 items-center gap-0.5 text-[11px] leading-none" style={{ color: PAL.meta }}>
                        {msg.at ? hhmm(msg.at) : ''}
                        {mine && <CheckCheck size={15} style={{ color: PAL.ticks }} aria-label="Entregado" />}
                      </span>
                    </div>
                    {msg.cards?.map((card) => (
                      <ProductCardPreview key={card.url} card={card} />
                    ))}
                  </div>
                </div>
              )
            })}
            {loading && (
              <div className="mt-2.5 flex justify-start">
                <div
                  className="relative flex items-center gap-1 rounded-lg px-3.5 py-3 shadow-sm"
                  style={{ background: PAL.incoming, borderTopLeftRadius: 0 }}
                  aria-label="Escribiendo…"
                >
                  <BubbleTail side="left" fill={PAL.incoming} />
                  {[0, 1, 2].map((d) => (
                    <span key={d} className="typing-dot h-2 w-2 rounded-full" style={{ background: PAL.meta, animationDelay: `${d * 160}ms` }} />
                  ))}
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              void send()
            }}
            className="flex items-center gap-1.5 px-2 py-2"
            style={{ background: PAL.bar }}
          >
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Mensaje"
              disabled={loading}
              enterKeyHint="send"
              className="min-w-0 flex-1 rounded-full px-4 py-3 text-base outline-none placeholder:text-white/40 disabled:opacity-50"
              style={{ background: PAL.field, color: PAL.text }}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              aria-label="Enviar"
              className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full shadow-sm transition-transform active:scale-95 disabled:opacity-50"
              style={{ background: GREEN, color: PAL.onBrand }}
            >
              <Send size={19} />
            </button>
          </form>
        </div>
      )}

      {/* El botón es la mascota misma (como el agente de cada negocio). */}
      <button
        onClick={() => setOpen(!open)}
        aria-label={open ? 'Cerrar chat' : 'Abrir chat'}
        className="flex h-16 w-16 items-center justify-center rounded-full shadow-xl transition-transform hover:scale-105 active:scale-95"
        style={{ background: open ? CARD : '#0b1220', border: `1px solid ${BORDER}` }}
      >
        {open ? <X className="h-6 w-6 text-white" /> : <MascotSmart mood="happy" size={48} color={GREEN} />}
      </button>
    </div>
  )
}
