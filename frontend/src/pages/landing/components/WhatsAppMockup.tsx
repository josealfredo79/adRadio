import { useState, useEffect, useRef, type ReactNode } from 'react'
import { Bot, PhoneCall, TrendingUp } from 'lucide-react'

function renderBold(text: string): ReactNode {
  const parts = text.split(/(\*[^*]+\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('*') && part.endsWith('*')) {
      return <strong key={i}>{part.slice(1, -1)}</strong>
    }
    return part
  })
}

const INITIAL_CHAT_MESSAGES = [
  { from: 'bot', text: '👋 Hola! Soy el asistente de *Pizzería El Fogón*. ¿En qué te puedo ayudar?' },
  { from: 'user', text: '¿Tienen pizza familiar de pepperoni?' },
  { from: 'bot', text: '🍕 ¡Claro! La familiar de pepperoni cuesta $189. Incluye 8 rebanadas. También tenemos 2x1 los martes 🔥' },
]

export default function WhatsAppMockup() {
  const [messages, setMessages] = useState(INITIAL_CHAT_MESSAGES)
  const [visible, setVisible] = useState(0)
  const [isTyping, setIsTyping] = useState(false)
  const [showOptions, setShowOptions] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (visible < messages.length) {
      const t = setTimeout(() => {
        setVisible(v => v + 1)
        if (visible + 1 === messages.length && messages.length === INITIAL_CHAT_MESSAGES.length) {
          setShowOptions(true)
        }
      }, visible === 0 ? 600 : 1200)
      return () => clearTimeout(t)
    }
  }, [visible, messages.length])

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [visible, isTyping, showOptions])

  const handleOptionClick = (userMsg: string, botMsg: string) => {
    setShowOptions(false)
    setMessages(prev => [...prev, { from: 'user', text: userMsg }])
    setVisible(v => v + 1)
    setIsTyping(true)
    setTimeout(() => {
      setIsTyping(false)
      setMessages(prev => [...prev, { from: 'bot', text: botMsg }])
      setVisible(v => v + 1)
    }, 1500)
  }

  return (
    <div className="relative mx-auto w-72">
      {/* Phone frame */}
      <div className="relative rounded-[2.5rem] border-4 border-white/20 bg-[#0a0a0a] shadow-2xl shadow-black/60 overflow-hidden">
        {/* Status bar */}
        <div className="flex items-center justify-between bg-[#128C7E] px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-full bg-white/20 flex items-center justify-center">
              <Bot className="h-4 w-4 text-white" />
            </div>
            <div>
              <div className="text-xs font-semibold text-white">Pizzería El Fogón</div>
              <div className="text-[10px] text-green-200">● en línea</div>
            </div>
          </div>
          <PhoneCall className="h-4 w-4 text-white/70" />
        </div>
        {/* Chat */}
        <div className="bg-[#ECE5DD] px-3 py-3 flex flex-col min-h-[360px] max-h-[360px] overflow-y-auto custom-scrollbar">
          <div className="flex-1 space-y-2">
            {messages.slice(0, visible).map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.from === 'user' ? 'justify-end' : 'justify-start'}`}
                style={{ animation: 'fadeUp 0.3s ease' }}
              >
                <div
                  className={`max-w-[85%] rounded-xl px-3 py-2 text-[11px] shadow-sm ${
                    msg.from === 'user'
                      ? 'rounded-tr-none bg-[#DCF8C6] text-gray-800'
                      : 'rounded-tl-none bg-white text-gray-800'
                  }`}
                  >{renderBold(msg.text)}</div>
              </div>
            ))}

            {isTyping && (
              <div className="flex justify-start" style={{ animation: 'fadeUp 0.3s ease' }}>
                <div className="rounded-xl rounded-tl-none bg-white px-3 py-2 shadow-sm flex gap-1 items-center">
                  <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce" style={{animationDelay:'0ms'}}></span>
                  <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce" style={{animationDelay:'150ms'}}></span>
                  <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce" style={{animationDelay:'300ms'}}></span>
                </div>
              </div>
            )}

            {showOptions && (
              <div className="flex flex-col gap-2 mt-4" style={{ animation: 'fadeUp 0.3s ease' }}>
                <button
                  onClick={() => handleOptionClick('¿Tienen promociones hoy?', '¡Sí! 🎉 Hoy tenemos 2x1 en pizzas grandes y envío gratis en pedidos mayores a $300.')}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white text-[10px] font-medium py-2 px-3 rounded-xl shadow-sm transition-colors text-left flex items-center justify-between"
                >
                  <span>¿Tienen promociones hoy?</span>
                  <span className="opacity-50 text-[8px] uppercase tracking-wider">Click</span>
                </button>
                <button
                  onClick={() => handleOptionClick('¿Cuánto tarda el envío?', '🛵 Nuestro tiempo de entrega estimado es de 30 a 45 minutos dependiendo de tu ubicación.')}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white text-[10px] font-medium py-2 px-3 rounded-xl shadow-sm transition-colors text-left flex items-center justify-between"
                >
                  <span>¿Cuánto tarda el envío?</span>
                  <span className="opacity-50 text-[8px] uppercase tracking-wider">Click</span>
                </button>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        </div>
      </div>
      {/* Floating badges */}
      <div className="absolute -left-10 top-16 rounded-xl bg-white px-3 py-2 shadow-xl text-xs font-semibold text-gray-800 flex items-center gap-1.5 z-10 hover:scale-105 transition-transform cursor-default">
        <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse"></span>
        Bot activo 24/7
      </div>
      <div className="absolute -right-10 bottom-20 rounded-xl bg-white px-3 py-2 shadow-xl text-xs font-semibold text-gray-800 flex items-center gap-1.5 z-10 hover:scale-105 transition-transform cursor-default">
        <TrendingUp className="h-3 w-3 text-indigo-500" />
        +340% ventas
      </div>
    </div>
  )
}
