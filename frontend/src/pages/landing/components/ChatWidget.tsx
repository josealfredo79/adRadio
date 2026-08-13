import { useState, useEffect, useRef, useCallback } from 'react'
import { MessageCircle, X, Send, Bot } from 'lucide-react'

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
const API_BASE = `${import.meta.env.VITE_API_URL ?? ''}/api/v1`
const SITE_ORIGIN = typeof window !== 'undefined' ? window.location.origin : ''

function ProductCardPreview({ card }: { card: ProductCard }) {
  return (
    <a
      href={`${SITE_ORIGIN}${card.url}`}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-2.5 rounded-lg bg-gray-800 border border-gray-700 p-2 hover:border-indigo-500 transition-colors w-full"
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
        {card.price && <div className="text-xs text-indigo-300">{card.price}</div>}
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
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
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

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end">
      {open && (
        <div
          className="mb-4 w-80 sm:w-96 rounded-2xl shadow-2xl overflow-hidden"
          style={{ animation: 'fadeUp 0.3s ease' }}
        >
          <div className="bg-gradient-to-r from-indigo-600 to-purple-600 p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-full bg-white/20 flex items-center justify-center">
                <Bot className="h-5 w-5 text-white" />
              </div>
              <div>
                <div className="text-sm font-semibold text-white">Alex · IaRadio</div>
                <div className="text-[10px] text-green-200">● en línea</div>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="text-white/70 hover:text-white transition-colors">
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="bg-gray-900 h-80 overflow-y-auto p-4 space-y-3 custom-scrollbar">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                style={{ animation: 'fadeUp 0.3s ease' }}
              >
                <div className={`flex flex-col gap-1.5 max-w-[85%] ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                  <div
                    className={`rounded-xl px-3 py-2 text-sm shadow-sm whitespace-pre-wrap ${
                      msg.role === 'user'
                        ? 'rounded-tr-none bg-indigo-600 text-white'
                        : 'rounded-tl-none bg-gray-800 text-gray-100'
                    }`}
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
              <div className="flex justify-start" style={{ animation: 'fadeUp 0.3s ease' }}>
                <div className="rounded-xl rounded-tl-none bg-gray-800 px-3 py-2 shadow-sm flex gap-1 items-center">
                  <span className="h-2 w-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span
                    className="h-2 w-2 rounded-full bg-gray-400 animate-bounce"
                    style={{ animationDelay: '150ms' }}
                  />
                  <span
                    className="h-2 w-2 rounded-full bg-gray-400 animate-bounce"
                    style={{ animationDelay: '300ms' }}
                  />
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <div className="bg-gray-900 border-t border-gray-800 p-3 flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && send()}
              placeholder="Escribe un mensaje..."
              disabled={loading}
              className="flex-1 bg-gray-800 text-white rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500 placeholder-gray-500 disabled:opacity-50"
            />
            <button
              onClick={send}
              disabled={loading || !input.trim()}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl px-3 py-2.5 transition-colors"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen(!open)}
        className="h-14 w-14 rounded-full bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 shadow-xl flex items-center justify-center transition-all hover:scale-105 active:scale-95"
        aria-label={open ? 'Cerrar chat' : 'Abrir chat'}
      >
        {open ? <X className="h-6 w-6 text-white" /> : <MessageCircle className="h-6 w-6 text-white" />}
      </button>
    </div>
  )
}
