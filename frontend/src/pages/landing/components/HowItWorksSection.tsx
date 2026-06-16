import { Users, Sparkles, MessageCircle } from 'lucide-react'
import RadioSphere3D from '@/components/RadioSphere3D'

const STEPS = [
  {
    n: '01', icon: <Users className="h-6 w-6 text-indigo-400" />,
    title: 'Sube tu info y contactos',
    desc: 'Importa tu lista de clientes en CSV y sube tu menú, catálogo o descripción de servicios. La IA lo aprende todo.',
    color: 'from-indigo-500/20 to-indigo-500/5',
  },
  {
    n: '02', icon: <Sparkles className="h-6 w-6 text-purple-400" />,
    title: 'La IA crea tu campaña',
    desc: 'Escribe tu intención ("Ofrecer 20% de descuento") y Claude genera 3 variantes de mensaje profesionales al instante.',
    color: 'from-purple-500/20 to-purple-500/5',
  },
  {
    n: '03', icon: <MessageCircle className="h-6 w-6 text-green-400" />,
    title: 'Lanza y el bot atiende',
    desc: 'Con un clic envías a todos tus contactos. El bot IA responde las preguntas en automático mientras tú descansas.',
    color: 'from-green-500/20 to-green-500/5',
  },
]

export default function HowItWorksSection() {
  return (
    <section id="como-funciona" className="px-5 py-24 relative overflow-hidden">
      {/* 3D Radio sphere background */}
      <RadioSphere3D />

      <div className="pointer-events-none absolute inset-0 mesh-bg opacity-30 z-0" />
      <div className="relative z-10 mx-auto max-w-5xl">
        <div className="mb-16 text-center">
          <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">Así de fácil</p>
          <h2 className="text-4xl font-black text-white sm:text-5xl">En 3 pasos tienes clientes</h2>
        </div>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          {STEPS.map(s => (
            <div key={s.n} className={`relative glass rounded-3xl p-7 bg-gradient-to-br ${s.color}`}>
              <div className="absolute top-5 right-5 text-5xl font-black text-white/5">{s.n}</div>
              <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl glass">
                {s.icon}
              </div>
              <h3 className="mb-2 text-lg font-bold text-white">{s.title}</h3>
              <p className="text-sm text-gray-400 leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
