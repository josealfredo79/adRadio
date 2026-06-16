import { useState } from 'react'
import { ChevronDown } from 'lucide-react'

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div
      className="border-b border-white/10 py-5 cursor-pointer group"
      onClick={() => setOpen(!open)}
    >
      <div className="flex items-center justify-between gap-4 group-hover:text-indigo-300 transition-colors">
        <span className="font-semibold text-white group-hover:text-indigo-300 transition-colors">{q}</span>
        <ChevronDown className={`h-4 w-4 text-indigo-400 shrink-0 transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
      </div>
      <div className={`overflow-hidden transition-all duration-300 ${open ? 'max-h-40 mt-3' : 'max-h-0'}`}>
        <p className="text-sm text-gray-400 leading-relaxed">{a}</p>
      </div>
    </div>
  )
}

const FAQ_ITEMS = [
  { q: '¿Necesito saber programar?', a: 'No. Si sabes mandar un WhatsApp, sabes usar IaRadio. Todo está diseñado para dueños de negocio, no para ingenieros.' },
  { q: '¿Cómo aprende el bot sobre mi negocio?', a: 'Subes tu menú, catálogo o descripción de servicios (PDF o texto). El sistema genera embeddings vectoriales y el bot responde solo con esa información, nunca inventa cosas.' },
  { q: '¿El número de WhatsApp es el mío?', a: 'Para campañas outbound usamos un número compartido de Twilio (sandbox). Para bot inbound con número propio incluimos configuración de número dedicado en los planes Pro y Business.' },
  { q: '¿Qué pasa si me quedo sin mensajes?', a: 'Puedes subir de plan en cualquier momento desde tu dashboard. Tus contactos, campañas y base de conocimiento se mantienen intactos.' },
  { q: '¿Puedo cancelar en cualquier momento?', a: 'Sí, sin penalizaciones ni contratos. Cancelas desde Configuración → Suscripción en menos de 1 minuto.' },
  { q: '¿Funciona para cualquier tipo de negocio?', a: 'Sí. Restaurantes, farmacias, estéticas, tiendas de ropa, clínicas, servicios profesionales... cualquier negocio que use WhatsApp para comunicarse con clientes.' },
]

export default function FaqSection() {
  return (
    <section id="faq" className="px-5 py-24 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 mesh-bg opacity-15" />
      <div className="mx-auto max-w-2xl">
        <div className="mb-12 text-center">
          <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">FAQ</p>
          <h2 className="text-4xl font-black text-white">Preguntas frecuentes</h2>
        </div>
        <div className="glass rounded-3xl p-8">
          {FAQ_ITEMS.map(item => (
            <FaqItem key={item.q} q={item.q} a={item.a} />
          ))}
        </div>
      </div>
    </section>
  )
}
