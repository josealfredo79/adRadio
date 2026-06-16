import { Link } from 'react-router-dom'
import { Zap, Clock, Shield, ArrowRight } from 'lucide-react'

export default function CtaSection() {
  return (
    <section className="px-5 py-28 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 mesh-bg" />
      <div className="pointer-events-none absolute inset-0" style={{background: 'radial-gradient(ellipse 60% 60% at 50% 50%, rgba(99,102,241,0.15) 0%, transparent 70%)'}} />
      <div className="relative mx-auto max-w-3xl text-center">
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-sm font-medium text-indigo-300">
          <Zap className="h-3.5 w-3.5" />
          15 días gratis · Sin tarjeta
        </div>
        <h2 className="mb-6 text-5xl font-black leading-tight sm:text-6xl">
          Tu negocio merece<br />
          <span className="text-shimmer">spots de voz con IA</span>
        </h2>
        <p className="mb-10 text-xl text-gray-400">
          Únete a los negocios mexicanos que ya usan IA para vender más por WhatsApp con campañas, bot y audios publicitarios.
        </p>
        <Link
          to="/register"
          className="inline-flex items-center gap-3 rounded-2xl bg-gradient-to-r from-[#674CC4] to-[#6366F1] px-10 py-5 text-lg font-black text-white shadow-2xl shadow-indigo-500/40 hover:shadow-indigo-500/60 hover:scale-105 transition-all glow-purple"
        >
          Crear mi cuenta gratis
          <ArrowRight className="h-5 w-5" />
        </Link>
        <div className="mt-6 flex flex-wrap justify-center gap-5 text-sm text-gray-600">
          <span className="flex items-center gap-1.5"><Clock className="h-4 w-4" /> Sin tarjeta de crédito</span>
          <span className="flex items-center gap-1.5"><Shield className="h-4 w-4" /> Datos seguros</span>
          <span className="flex items-center gap-1.5"><Zap className="h-4 w-4" /> Listo en 10 minutos</span>
        </div>
      </div>
    </section>
  )
}
