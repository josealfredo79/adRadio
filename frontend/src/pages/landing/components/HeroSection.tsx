import { Link } from 'react-router-dom'
import { CheckCircle, ArrowRight, Zap, Sparkles } from 'lucide-react'
import WhatsAppMockup from './WhatsAppMockup'
import { AnimatedStat } from '../hooks/useCountUp'

export default function HeroSection() {
  return (
    <section className="relative px-5 pt-20 sm:pt-24 pb-16 sm:pb-8 overflow-hidden min-h-screen sm:min-h-[90vh] flex items-start sm:items-center">
      {/* Video background inmersivo */}
      <video
        autoPlay
        muted
        loop
        playsInline
        poster="https://images.unsplash.com/photo-1557804506-669a67965ba0?auto=format&fit=crop&w=1200&q=80"
        className="absolute top-0 left-0 w-full h-full object-cover z-0"
      >
        <source src="https://assets.mixkit.co/videos/preview/mixkit-abstract-digital-network-of-lines-and-lights-41945-large.mp4" type="video/mp4" />
      </video>

      {/* Overlay oscuro para contraste */}
      <div className="absolute inset-0 bg-[#06060f]/75 z-[1]" />

      {/* Mesh bg overlay para textura */}
      <div className="absolute inset-0 mesh-bg opacity-30 z-[2]" />

      {/* Dot grid */}
      <div className="pointer-events-none absolute inset-0 opacity-[0.08] z-[3]"
        style={{backgroundImage: 'radial-gradient(circle, rgba(103,76,196,0.3) 1px, transparent 1px)', backgroundSize: '32px 32px'}} />

      <div className="relative z-[4] mx-auto max-w-6xl w-full">
        <div className="grid grid-cols-1 lg:grid-cols-2 items-center gap-12 lg:gap-16">
          {/* Left: text */}
          <div>
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-[#674CC4]/30 bg-[#674CC4]/10 px-4 py-1.5 text-sm font-medium text-[#674CC4]">
              <Sparkles className="h-3.5 w-3.5" />
              Impulsado por Claude IA · Meta · pgvector
            </div>

            <h1 className="mb-6 text-5xl font-black leading-[1.05] tracking-tight sm:text-6xl lg:text-7xl">
              Spots de radio con IA<br />
              <span className="text-shimmer">para tu negocio en WhatsApp</span>
            </h1>

            <p className="mb-8 text-lg text-gray-400 leading-relaxed max-w-lg">
              Campañas masivas por WhatsApp, bot IA que conoce tu negocio,
              audios publicitarios y cupones automáticos. <strong className="text-white">Todo en una plataforma.</strong>
            </p>

            <div className="flex flex-wrap gap-3 mb-8">
              <Link
                to="/register"
                className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#674CC4] to-[#6366F1] px-7 py-3.5 text-base font-black text-white shadow-xl shadow-[#674CC4]/30 hover:shadow-[#674CC4]/50 hover:scale-[1.03] active:scale-[0.98] transition-all duration-300 glow-purple"
              >
                Empieza gratis
                <ArrowRight className="h-4 w-4" />
              </Link>
              <a
                href="#como-funciona"
                className="flex items-center gap-2 rounded-xl glass px-6 py-3.5 text-base font-semibold text-gray-300 hover:text-white hover:border-white/20 hover:scale-[1.03] active:scale-[0.98] transition-all duration-300"
              >
                Ver demo
              </a>
            </div>

            <div className="flex flex-wrap gap-5 text-sm text-gray-500">
              <span className="flex items-center gap-1.5"><CheckCircle className="h-4 w-4 text-green-500" /> Sin tarjeta de crédito</span>
              <span className="flex items-center gap-1.5"><CheckCircle className="h-4 w-4 text-green-500" /> Cancela cuando quieras</span>
              <span className="flex items-center gap-1.5"><CheckCircle className="h-4 w-4 text-green-500" /> Configuración en 10 min</span>
              <span className="flex items-center gap-1.5"><Zap className="h-4 w-4 text-[#674CC4]" /> 15 días gratis</span>
            </div>
          </div>

          {/* Right: WhatsApp product demo */}
          <div className="flex justify-center lg:justify-end">
            <div className="relative float-anim">
              <div className="absolute -top-3 -right-3 z-20 inline-flex items-center gap-1.5 rounded-full bg-green-500 px-3 py-1.5 text-[10px] font-bold text-white shadow-lg animate-pulse">
                <span className="h-1.5 w-1.5 rounded-full bg-white" />
                Producto en vivo
              </div>
              <WhatsAppMockup />
            </div>
          </div>
        </div>

        {/* Stats row */}
        <div className="mt-10 sm:mt-20 max-w-4xl mx-auto">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <AnimatedStat n={10} suffix=" min" label="Para lanzar tu primera campaña" />
            <AnimatedStat n={60} suffix="%" label="Tasa de canje de cupones" />
            <AnimatedStat n={95} suffix="%" label="Tasa de entrega WhatsApp" />
            <AnimatedStat n={15} suffix=" días" label="Prueba gratuita sin tarjeta" />
          </div>
          <div className="mt-3 flex items-center justify-center gap-2 text-xs text-gray-600">
            <span className="inline-block h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />
            <span>Impulsado por <strong className="text-indigo-400">Claude IA · Meta · pgvector</strong></span>
          </div>
        </div>
      </div>
    </section>
  )
}
