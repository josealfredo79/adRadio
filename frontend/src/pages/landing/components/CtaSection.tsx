import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Zap, Clock, Shield, ArrowRight, Lock } from 'lucide-react'

// Deadline: 72 hours from now (stored in sessionStorage so it persists on reload)
function getDeadline(): Date {
  const key = 'iaradio_cta_deadline'
  const stored = sessionStorage.getItem(key)
  if (stored) {
    const d = new Date(stored)
    if (d > new Date()) return d
  }
  const deadline = new Date(Date.now() + 72 * 60 * 60 * 1000)
  sessionStorage.setItem(key, deadline.toISOString())
  return deadline
}

function useCountdown() {
  const [timeLeft, setTimeLeft] = useState({ h: 0, m: 0, s: 0 })

  useEffect(() => {
    const deadline = getDeadline()
    const tick = () => {
      const diff = deadline.getTime() - Date.now()
      if (diff <= 0) {
        setTimeLeft({ h: 0, m: 0, s: 0 })
        return
      }
      const h = Math.floor(diff / 3_600_000)
      const m = Math.floor((diff % 3_600_000) / 60_000)
      const s = Math.floor((diff % 60_000) / 1_000)
      setTimeLeft({ h, m, s })
    }
    tick()
    const id = setInterval(tick, 1_000)
    return () => clearInterval(id)
  }, [])

  return timeLeft
}

function TimeUnit({ value, label }: { value: number; label: string }) {
  return (
    <div className="flex flex-col items-center">
      <div className="w-14 h-14 rounded-xl bg-white/10 border border-white/20 flex items-center justify-center text-2xl font-black text-white tabular-nums backdrop-blur-sm">
        {String(value).padStart(2, '0')}
      </div>
      <span className="mt-1.5 text-[10px] uppercase tracking-widest text-indigo-300">{label}</span>
    </div>
  )
}

const TRUST_BADGES = [
  { label: 'Pagos seguros', sublabel: 'Stripe', icon: '💳' },
  { label: 'WhatsApp Business', sublabel: 'Meta Cloud API', icon: '💬' },
  { label: 'IA generativa', sublabel: 'Anthropic Claude', icon: '🤖' },
  { label: 'Datos cifrados', sublabel: 'SSL + bcrypt', icon: '🔒' },
]

export default function CtaSection() {
  const { h, m, s } = useCountdown()
  const expired = h === 0 && m === 0 && s === 0

  return (
    <section className="px-5 py-28 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 mesh-bg" />
      <div className="pointer-events-none absolute inset-0" style={{ background: 'radial-gradient(ellipse 60% 60% at 50% 50%, rgba(99,102,241,0.18) 0%, transparent 70%)' }} />

      <div className="relative mx-auto max-w-3xl text-center">
        {/* Badge */}
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-sm font-medium text-indigo-300">
          <Zap className="h-3.5 w-3.5" />
          15 días gratis · Sin tarjeta
        </div>

        {/* Headline */}
        <h2 className="mb-6 text-5xl font-black leading-tight sm:text-6xl">
          Tu negocio merece<br />
          <span className="text-shimmer">spots de voz con IA</span>
        </h2>
        <p className="mb-8 text-xl text-gray-400">
          Únete a los negocios mexicanos que ya usan IA para vender más por WhatsApp con campañas, bot y audios publicitarios.
        </p>

        {/* Urgency countdown */}
        {!expired && (
          <div className="mb-8 inline-block rounded-2xl border border-indigo-500/20 bg-indigo-500/5 px-8 py-5">
            <p className="text-xs text-indigo-300 font-semibold uppercase tracking-widest mb-3">
              🔥 Oferta de lanzamiento expira en
            </p>
            <div className="flex items-center gap-3 justify-center">
              <TimeUnit value={h} label="horas" />
              <span className="text-2xl font-black text-indigo-400 mb-4">:</span>
              <TimeUnit value={m} label="min" />
              <span className="text-2xl font-black text-indigo-400 mb-4">:</span>
              <TimeUnit value={s} label="seg" />
            </div>
            <p className="mt-3 text-xs text-indigo-400/70">50% de descuento el primer mes para los primeros 50 usuarios</p>
          </div>
        )}

        {/* CTA button */}
        <div className="mb-6">
          <Link
            to="/register"
            className="inline-flex items-center gap-3 rounded-2xl bg-gradient-to-r from-[#674CC4] to-[#6366F1] px-10 py-5 text-lg font-black text-white shadow-2xl shadow-indigo-500/40 hover:shadow-indigo-500/60 hover:scale-105 transition-all glow-purple"
          >
            Crear mi cuenta gratis
            <ArrowRight className="h-5 w-5" />
          </Link>
        </div>

        {/* Trust micro-text */}
        <div className="mb-10 flex flex-wrap justify-center gap-5 text-sm text-gray-600">
          <span className="flex items-center gap-1.5"><Clock className="h-4 w-4" />Sin tarjeta de crédito</span>
          <span className="flex items-center gap-1.5"><Shield className="h-4 w-4" />Datos seguros</span>
          <span className="flex items-center gap-1.5"><Zap className="h-4 w-4" />Listo en 10 minutos</span>
          <span className="flex items-center gap-1.5"><Lock className="h-4 w-4" />Cancela cuando quieras</span>
        </div>

        {/* Trust badges */}
        <div className="border-t border-white/5 pt-8">
          <p className="text-xs text-gray-600 uppercase tracking-widest mb-5">Tecnología en la que confías</p>
          <div className="flex flex-wrap justify-center gap-4">
            {TRUST_BADGES.map(b => (
              <div key={b.label} className="flex items-center gap-2.5 rounded-xl border border-white/8 bg-white/4 px-4 py-2.5 backdrop-blur-sm">
                <span className="text-lg">{b.icon}</span>
                <div className="text-left">
                  <div className="text-[11px] font-semibold text-gray-300">{b.label}</div>
                  <div className="text-[10px] text-gray-500">{b.sublabel}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
