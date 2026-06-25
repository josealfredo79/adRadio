import { Link } from 'react-router-dom'
import { Star } from 'lucide-react'

const TESTIMONIALS = [
  {
    initials: 'EF', color: '#f97316', name: 'Restaurante El Fogón', loc: 'Oaxaca, México', rating: 5,
    text: '"Mandamos una campaña del menú del día y en 20 minutos teníamos 15 reservaciones. Antes tardábamos horas llamando uno a uno."',
    result: '+340% reservaciones',
    resultColor: 'text-green-400 bg-green-500/15',
  },
  {
    initials: 'SP', color: '#22c55e', name: 'Farmacia Salud Plus', loc: 'Puebla, México', rating: 5,
    text: '"El bot responde disponibilidad de medicamentos a las 2am. Mis clientes están encantados y ya no pierdo ventas nocturnas."',
    result: 'Atención 24/7',
    resultColor: 'text-blue-400 bg-blue-500/15',
  },
  {
    initials: 'EG', color: '#a855f7', name: 'Estética Glamour', loc: 'CDMX, México', rating: 5,
    text: '"Los cupones de WhatsApp tienen 60% de canje. Nunca pensé que captar clientes nuevas pudiera ser tan barato y efectivo."',
    result: '60% cupones canjeados',
    resultColor: 'text-amber-400 bg-amber-500/15',
  },
  {
    initials: 'TM', color: '#6366f1', name: 'Taquería El Mestizo', loc: 'Guadalajara, México', rating: 5,
    text: '"En 3 días de campaña llenamos el local el fin de semana. El bot agenda reservas automaticamente, ya no contesto el teléfono para eso."',
    result: '+180% fin de semana',
    resultColor: 'text-green-400 bg-green-500/15',
  },
  {
    initials: 'CC', color: '#ec4899', name: 'Clínica Capufe', loc: 'Monterrey, México', rating: 5,
    text: '"Redujimos las citas no asistidas en un 70% con recordatorios automáticos por WhatsApp. El sistema se paga solo en la primera semana."',
    result: '-70% no-shows',
    resultColor: 'text-violet-400 bg-violet-500/15',
  },
]

function Avatar({ initials, color }: { initials: string; color: string }) {
  return (
    <div
      className="h-10 w-10 rounded-full flex items-center justify-center text-sm font-black text-white shrink-0"
      style={{ background: `linear-gradient(135deg, ${color}cc, ${color}66)`, border: `2px solid ${color}40` }}
    >
      {initials}
    </div>
  )
}

export default function TestimonialsSection() {
  return (
    <section className="px-5 py-24 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 mesh-bg opacity-40" />
      <div className="relative mx-auto max-w-6xl">
        <div className="mb-14 text-center">
          <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">Historias reales</p>
          <h2 className="text-4xl font-black text-white sm:text-5xl">Negocios que ya triunfan</h2>
          <p className="mt-4 text-gray-500 text-sm">Más de 200 negocios en México y Latinoamérica confían en IaRadio</p>
        </div>

        {/* Desktop: grid 3+2 */}
        <div className="hidden sm:block space-y-5">
          <div className="grid grid-cols-3 gap-5">
            {TESTIMONIALS.slice(0, 3).map(t => (
              <TestimonialCard key={t.name} t={t} />
            ))}
          </div>
          <div className="grid grid-cols-2 gap-5 max-w-2xl mx-auto">
            {TESTIMONIALS.slice(3).map(t => (
              <TestimonialCard key={t.name} t={t} />
            ))}
          </div>
        </div>

        {/* Mobile: marquee scroll */}
        <div className="sm:hidden overflow-x-auto pb-4 -mx-5 px-5">
          <div className="flex gap-4" style={{ width: 'max-content' }}>
            {TESTIMONIALS.map(t => (
              <div key={t.name} className="w-72 shrink-0">
                <TestimonialCard t={t} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function TestimonialCard({ t }: { t: typeof TESTIMONIALS[0] }) {
  return (
    <div className="glass rounded-3xl p-6 flex flex-col h-full">
      <div className="flex gap-0.5 mb-3">
        {[...Array(t.rating)].map((_, i) => (
          <Star key={i} className="h-3.5 w-3.5 fill-yellow-400 text-yellow-400" />
        ))}
      </div>
      <p className="text-sm text-gray-300 leading-relaxed italic flex-1 mb-4">{t.text}</p>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <Avatar initials={t.initials} color={t.color} />
          <div>
            <div className="text-sm font-bold text-white leading-tight">{t.name}</div>
            <div className="text-xs text-gray-500">{t.loc}</div>
          </div>
        </div>
        <div className={`rounded-xl px-2.5 py-1.5 text-[11px] font-bold whitespace-nowrap ${t.resultColor}`}>
          {t.result}
        </div>
      </div>
    </div>
  )
}
