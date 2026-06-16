import { Bot, MessageCircle, Mic, Gift, BarChart3, Shield } from 'lucide-react'

const FEATURES = [
  {
    icon: <Bot className="h-5 w-5 text-indigo-400" />,
    title: 'Bot IA con tu conocimiento',
    desc: 'Responde preguntas 24/7 usando tu catálogo, menú o lista de precios. Entiende contexto, no solo palabras clave.',
    badge: 'IA',
  },
  {
    icon: <MessageCircle className="h-5 w-5 text-green-400" />,
    title: 'Campañas masivas WhatsApp',
    desc: 'Envía a cientos de contactos personalizando nombre, ciudad y producto. Anti-ban automático.',
    badge: null,
  },
  {
    icon: <Mic className="h-5 w-5 text-purple-400" />,
    title: 'Cuñas de radio con IA',
    desc: 'Genera spots de audio profesionales en segundos y envíalos como notas de voz en WhatsApp.',
    badge: 'NUEVO',
  },
  {
    icon: <Gift className="h-5 w-5 text-orange-400" />,
    title: 'Cupones automáticos',
    desc: 'Código único por contacto. Se canjea respondiendo "CANJEAR". Rastreo de redención en tiempo real.',
    badge: null,
  },
  {
    icon: <BarChart3 className="h-5 w-5 text-blue-400" />,
    title: 'Analytics en tiempo real',
    desc: 'Enviados, entregados, leídos, respondidos y cupones canjeados en un dashboard limpio.',
    badge: null,
  },
  {
    icon: <Shield className="h-5 w-5 text-emerald-400" />,
    title: 'Seguro y confiable',
    desc: 'Validación de firma Twilio, rate limiting, bcrypt cost 12, JWT con rotación automática.',
    badge: null,
  },
]

export default function FeaturesSection() {
  return (
    <section className="px-5 py-24 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 mesh-bg opacity-20" />
      <div className="mx-auto max-w-5xl">
        <div className="mb-16 text-center">
          <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">Funcionalidades</p>
          <h2 className="text-4xl font-black text-white sm:text-5xl">Una plataforma. Todo incluido.</h2>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(f => (
            <div key={f.title} className="group glass rounded-2xl p-6 hover:border-indigo-500/50 hover:bg-indigo-500/10 hover:shadow-[0_0_30px_-5px_rgba(99,102,241,0.3)] transition-all duration-300 relative overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"></div>
              <div className="mb-4 flex items-start justify-between relative z-10">
                <div className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-white/5 group-hover:scale-110 transition-transform duration-300">
                  {f.icon}
                </div>
                {f.badge && (
                  <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-[10px] font-bold text-indigo-300 uppercase tracking-wider shadow-[0_0_10px_rgba(99,102,241,0.5)]">
                    {f.badge}
                  </span>
                )}
              </div>
              <h3 className="mb-2 font-bold text-white">{f.title}</h3>
              <p className="text-sm text-gray-500 leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
