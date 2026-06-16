import { Link } from 'react-router-dom'
import { Star, Mic } from 'lucide-react'

const TESTIMONIALS = [
  {
    emoji: '🍽️', name: 'Restaurante El Fogón', loc: 'Oaxaca, México', rating: 5,
    text: '"Mandamos una campaña del menú del día y en 20 minutos teníamos 15 reservaciones. Antes tardábamos horas llamando uno a uno."',
    result: '+340% reservaciones',
  },
  {
    emoji: '💊', name: 'Farmacia Salud Plus', loc: 'Puebla, México', rating: 5,
    text: '"El bot responde disponibilidad de medicamentos a las 2am. Mis clientes están encantados y ya no pierdo ventas nocturnas."',
    result: 'Atención 24/7',
  },
  {
    emoji: '💇', name: 'Estética Glamour', loc: 'CDMX, México', rating: 5,
    text: '"Los cupones de WhatsApp tienen 60% de canje. Nunca pensé que captar clientes nuevas pudiera ser tan barato y efectivo."',
    result: '60% cupones canjeados',
  },
]

export default function TestimonialsSection() {
  return (
    <section className="px-5 py-24 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 mesh-bg opacity-40" />
      <div className="relative mx-auto max-w-5xl">
        <div className="mb-14 text-center">
          <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">Historias reales</p>
          <h2 className="text-4xl font-black text-white sm:text-5xl">Negocios que ya triunfan</h2>
        </div>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
          {TESTIMONIALS.map(t => (
            <div key={t.name} className="glass rounded-3xl p-7 flex flex-col">
              <div className="flex gap-0.5 mb-4">
                {[...Array(t.rating)].map((_, i) => (
                  <Star key={i} className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                ))}
              </div>
              <p className="text-sm text-gray-300 leading-relaxed italic flex-1 mb-5">{t.text}</p>
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">{t.emoji}</span>
                    <div>
                      <div className="text-sm font-bold text-white">{t.name}</div>
                      <div className="text-xs text-gray-500">{t.loc}</div>
                    </div>
                  </div>
                </div>
                <div className="rounded-xl bg-green-500/15 px-3 py-1.5 text-xs font-bold text-green-400">
                  {t.result}
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-10 text-center">
          <Link
            to="/customer-stories"
            className="inline-flex items-center gap-2 rounded-xl glass px-6 py-3 text-sm font-semibold text-gray-300 hover:text-white hover:border-white/20 hover:scale-[1.03] active:scale-[0.98] transition-all duration-300"
          >
            Escuchar historias reales <Mic className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </section>
  )
}
