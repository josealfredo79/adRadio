import { Bot, CheckCircle, Sparkles, Zap, TrendingUp, Plus } from 'lucide-react'

const KB_ITEMS = [
  { label: 'Menú / Catálogo', status: '✅ 12 productos' },
  { label: 'Precios y promociones', status: '✅ 3 promos activas' },
  { label: 'Horarios y ubicación', status: '✅ Sucursal única' },
  { label: 'FAQ del negocio', status: '✅ 15 preguntas' },
]

const AI_FEATURES = [
  {
    icon: <Sparkles className="h-5 w-5 text-indigo-400" />,
    title: 'Aprende de tus datos',
    desc: 'Sube tu menú, catálogo o cualquier documento. El bot entiende el contexto completo de tu negocio — no solo palabras clave sueltas.',
  },
  {
    icon: <Zap className="h-5 w-5 text-yellow-400" />,
    title: 'Responde en segundos',
    desc: 'Sin esperas, sin transferencias. El agente atiende a todos tus clientes al mismo tiempo, 24/7, en WhatsApp.',
  },
  {
    icon: <TrendingUp className="h-5 w-5 text-green-400" />,
    title: 'Vende mientras duermes',
    desc: 'Cada pregunta de un cliente es una venta potencial. El bot califica leads, toma pedidos y agenda citas sin intervención humana.',
  },
]

export default function AIAgentSection() {
  return (
    <section className="px-5 py-24 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 mesh-bg opacity-30" />
      <div className="relative mx-auto max-w-5xl">
        <div className="mb-14 text-center">
          <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">Tu agente IA</p>
          <h2 className="text-4xl font-black text-white sm:text-5xl">
            Un vendedor 24/7 que <span className="text-shimmer">conoce tu negocio</span>
          </h2>
        </div>
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-2 items-center">
          <div className="glass rounded-3xl p-6 border border-indigo-500/20">
            <div className="flex items-center gap-3 mb-5">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-[#674CC4] to-[#6366F1] flex items-center justify-center">
                <Bot className="h-5 w-5 text-white" />
              </div>
              <div>
                <div className="text-sm font-bold text-white">Base de conocimiento</div>
                <div className="text-xs text-green-400 flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                  Conectado a Claude IA
                </div>
              </div>
            </div>
            <div className="space-y-2">
              {KB_ITEMS.map(item => (
                <div key={item.label} className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3 hover:border-indigo-500/30 transition-colors">
                  <div className="flex items-center gap-2">
                    <div className="h-6 w-6 rounded-full bg-indigo-500/10 flex items-center justify-center">
                      <CheckCircle className="h-3 w-3 text-indigo-400" />
                    </div>
                    <span className="text-sm text-gray-300">{item.label}</span>
                  </div>
                  <span className="text-[10px] text-gray-500">{item.status}</span>
                </div>
              ))}
            </div>
            <div className="mt-4 flex items-center gap-2 rounded-xl bg-indigo-500/5 border border-dashed border-indigo-500/20 px-4 py-3">
              <Plus className="h-4 w-4 text-indigo-400" />
              <span className="text-sm text-gray-500">Subir nuevo documento...</span>
            </div>
          </div>
          <div className="space-y-6">
            {AI_FEATURES.map(f => (
              <div key={f.title} className="glass rounded-2xl p-6">
                <div className="flex items-center gap-3 mb-3">
                  {f.icon}
                  <h3 className="font-bold text-white">{f.title}</h3>
                </div>
                <p className="text-sm text-gray-400 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
