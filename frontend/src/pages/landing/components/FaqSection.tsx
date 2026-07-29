import { useState, useRef, useEffect } from 'react'
import { ChevronDown } from 'lucide-react'

const FAQ_ITEMS = [
  { q: '¿Necesito saber programar?', a: 'No. Si sabes mandar un WhatsApp, sabes usar IaRadio. Todo está diseñado para dueños de negocio, no para ingenieros.' },
  { q: '¿Cómo aprende el bot sobre mi negocio?', a: 'Subes tu menú, catálogo o descripción de servicios (PDF o texto). El sistema genera embeddings vectoriales y el bot responde solo con esa información, nunca inventa cosas.' },
  { q: '¿El número de WhatsApp es el mío?', a: 'Sí. Conectas tu propio número de WhatsApp Business directo con Meta (WhatsApp Cloud API) desde tu panel — nosotros nunca vemos ni compartimos tu token de acceso, se guarda cifrado.' },
  { q: '¿Qué pasa si me quedo sin mensajes?', a: 'Puedes subir de plan en cualquier momento desde tu dashboard. Tus contactos, campañas y base de conocimiento se mantienen intactos.' },
  { q: '¿Puedo cancelar en cualquier momento?', a: 'Sí, sin penalizaciones ni contratos. Cancelas desde Configuración → Suscripción en menos de 1 minuto.' },
  { q: '¿Funciona para cualquier tipo de negocio?', a: 'Sí. Restaurantes, farmacias, estéticas, tiendas de ropa, clínicas, servicios profesionales... cualquier negocio que use WhatsApp para comunicarse con clientes.' },
  { q: '¿Funciona en toda Latinoamérica?', a: 'IaRadio funciona en cualquier país donde Meta soporte WhatsApp Business Platform. Actualmente la mayoría de países de América Latina están cubiertos: México, Colombia, Argentina, Chile, Perú y más.' },
  { q: '¿Están seguros mis datos?', a: 'Sí. Todos los datos se almacenan cifrados en servidores en EE.UU. (Neon PostgreSQL). Nunca vendemos ni compartimos tus contactos. Cumplimos con buenas prácticas de seguridad (HTTPS, JWT, bcrypt).' },
]

function FaqItem({ q, a, isOpen, onToggle }: { q: string; a: string; isOpen: boolean; onToggle: () => void }) {
  const contentRef = useRef<HTMLDivElement>(null)

  return (
    <div className="border-b border-white/10 py-5">
      <button
        className="flex w-full items-center justify-between gap-4 text-left group"
        onClick={onToggle}
        aria-expanded={isOpen}
      >
        <span className="font-semibold text-white group-hover:text-indigo-300 transition-colors">{q}</span>
        <ChevronDown
          className={`h-4 w-4 text-indigo-400 shrink-0 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>
      <div
        ref={contentRef}
        className="overflow-hidden transition-all duration-300 ease-in-out"
        style={{
          maxHeight: isOpen ? `${contentRef.current?.scrollHeight ?? 200}px` : '0px',
          opacity: isOpen ? 1 : 0,
        }}
      >
        <p className="mt-3 text-sm text-gray-400 leading-relaxed">{a}</p>
      </div>
    </div>
  )
}

export default function FaqSection() {
  const [openItems, setOpenItems] = useState<Set<number>>(new Set([0]))

  const toggle = (i: number) => {
    setOpenItems(prev => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  return (
    <section id="faq" className="px-5 py-24 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 mesh-bg opacity-15" />
      <div className="mx-auto max-w-2xl">
        <div className="mb-12 text-center">
          <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">FAQ</p>
          <h2 className="text-4xl font-black text-white">Preguntas frecuentes</h2>
          <p className="mt-3 text-sm text-gray-500">¿No encuentras tu respuesta? Escríbenos por WhatsApp.</p>
        </div>
        <div className="glass rounded-3xl px-8 py-2">
          {FAQ_ITEMS.map((item, i) => (
            <FaqItem
              key={item.q}
              q={item.q}
              a={item.a}
              isOpen={openItems.has(i)}
              onToggle={() => toggle(i)}
            />
          ))}
        </div>
      </div>
    </section>
  )
}
