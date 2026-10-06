import { useState, useEffect, useRef, useCallback } from 'react'
import { X, Send } from 'lucide-react'
import MascotSmart from '@/components/MascotSmart'

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
}

const STORAGE_KEY = 'iaradio_demo_session'
// Los colores del chat de la app del cliente (verde IaRadio, fondo oscuro).
const GREEN = '#25D366'
const BG = '#0b0d16'
const CARD = '#151926'
const BORDER = 'rgba(255,255,255,0.09)'
const MUTED = 'rgba(255,255,255,0.55)'
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
    setMessages((prev) => [...prev, { role: 'user', content: text }])
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
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply, cards: data.cards }])
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
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
          <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: `1px solid ${BORDER}` }}>
            <div className="flex min-w-0 items-center gap-2">
              <div className="-my-1 shrink-0">
                <MascotSmart mood={loading ? 'thinking' : 'idle'} size={44} color={GREEN} />
              </div>
              <div className="min-w-0">
                <p className="truncate font-semibold">Alex · IaRadio</p>
                <p className="truncate text-xs" style={{ color: MUTED }}>
                  {loading ? 'escribiendo…' : 'Asistente · responde al instante'}
                </p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Cerrar chat" className="rounded-full p-2" style={{ color: MUTED }}>
              <X size={20} />
            </button>
          </div>

          <div className="custom-scrollbar flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-4">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                style={{ animation: 'fadeUp 0.3s ease' }}
              >
                <div className={`flex max-w-[85%] flex-col gap-1.5 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                  <div
                    className="whitespace-pre-line rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed"
                    style={
                      msg.role === 'user'
                        ? { background: GREEN, color: '#fff', borderBottomRightRadius: 6 }
                        : { background: CARD, border: `1px solid ${BORDER}`, borderBottomLeftRadius: 6 }
                    }
                  >
                    {msg.content}
                  </div>
                  {msg.cards?.map((card) => (
                    <ProductCardPreview key={card.url} card={card} />
                  ))}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="rounded-2xl px-4 py-2.5 text-sm" style={{ background: CARD, color: MUTED }}>
                  Escribiendo…
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
            className="flex items-center gap-2 p-3"
            style={{ borderTop: `1px solid ${BORDER}` }}
          >
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Escribe tu mensaje…"
              disabled={loading}
              enterKeyHint="send"
              className="min-w-0 flex-1 rounded-full bg-transparent px-4 py-3 text-base text-white outline-none placeholder:text-white/40 disabled:opacity-50"
              style={{ border: `1px solid ${BORDER}` }}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              aria-label="Enviar"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-white transition-transform active:scale-95 disabled:opacity-50"
              style={{ background: GREEN }}
            >
              <Send size={18} />
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
