import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Zap, CheckCircle, Sparkles } from 'lucide-react'
import { LANDING_PLANS, type PlanDefinition } from '@/lib/plans'

interface BackendPlan {
  price_mxn: number
  price_usd: number
}

export default function PricingSection() {
  const [backendPrices, setBackendPrices] = useState<Record<string, BackendPlan> | null>(null)

  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_URL ?? ''}/api/v1/plans`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => data && setBackendPrices(data))
      .catch(() => {})
  }, [])

  const planPrice = (plan: PlanDefinition, field: 'price_mxn' | 'price_usd') => {
    return (backendPrices?.[plan.key]?.[field] ?? plan[field]) as number
  }

  return (
    <section id="precios" className="px-5 py-24 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 mesh-bg-light opacity-50" />
      <div className="mx-auto max-w-6xl">
        <div className="mb-14 text-center">
          <p className="text-indigo-400 font-semibold text-sm uppercase tracking-widest mb-3">Precios</p>
          <h2 className="text-4xl font-black text-white sm:text-5xl">Invierte lo que vendes en un día</h2>
          <p className="mt-4 text-gray-500">Sin contratos. Cancela cuando quieras.</p>
          <p className="mt-3 inline-flex items-center gap-2 rounded-full bg-white/5 border border-white/10 px-4 py-1.5 text-xs text-gray-400">
            <Sparkles className="h-3.5 w-3.5 text-[#674CC4]" />
            Configuración de tu bot incluida en todos los planes — otros cobran hasta $35,900 MXN aparte solo por el setup
          </p>
        </div>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-5 items-start">
          {LANDING_PLANS.map(plan => {
            const mxn = planPrice(plan, 'price_mxn')
            const usd = planPrice(plan, 'price_usd')
            const refPrice = plan.referencePriceMxn
            const savings = refPrice ? Math.round((1 - mxn / refPrice) * 100) : null
            return (
              <div
                key={plan.key}
                className={`relative rounded-3xl p-6 flex flex-col transition-all ${
                  plan.popular
                    ? 'bg-gradient-to-br from-[#674CC4]/30 to-[#6366F1]/20 border-2 border-[#674CC4]/60 shadow-2xl shadow-[#674CC4]/20 scale-[1.03]'
                    : 'glass'
                }`}
              >
                {/* Discount badge */}
                {savings && savings > 0 && (
                  <div className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-green-500/15 px-3 py-1 text-xs font-bold text-green-400 w-fit">
                    <Zap className="h-3 w-3" />
                    Ahorra {savings}%
                  </div>
                )}

                <div className="text-sm font-bold text-gray-400 uppercase tracking-widest mb-1">{plan.name}</div>
                <div className="text-xs text-gray-500 mb-4">{plan.tagline}</div>

                <div className="flex items-baseline gap-2 mb-1">
                  {refPrice && (
                    <span className="text-sm text-gray-500 line-through">${refPrice.toLocaleString()}</span>
                  )}
                  <span className="text-4xl font-black text-white">${mxn.toLocaleString()}</span>
                  <span className="text-xs text-gray-500">MXN/mes</span>
                </div>

                <div className="flex items-center gap-3 mb-5">
                  <span className="text-[10px] text-gray-600">≈ ${usd} USD</span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-[#674CC4]/15 px-2 py-0.5 text-[9px] font-bold text-[#674CC4]">
                    <Zap className="h-2.5 w-2.5" />
                    15 días gratis
                  </span>
                </div>

                <Link
                  to="/register"
                  className={`block w-full rounded-xl py-3 text-center text-sm font-black transition-all hover:scale-105 mb-3 ${
                    plan.popular
                      ? 'bg-gradient-to-r from-[#674CC4] to-[#6366F1] text-white shadow-lg shadow-[#674CC4]/30 hover:shadow-[#674CC4]/50'
                      : 'glass text-gray-300 hover:text-white hover:border-white/20'
                  }`}
                >
                  Empezar con {plan.name} →
                </Link>

                {plan.popular && (
                  <div className="text-center text-[10px] font-bold text-[#674CC4] uppercase tracking-widest mb-5">
                    ⭐ Más popular
                  </div>
                )}

                <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-3">
                  Todo incluido:
                </div>

                <ul className="space-y-2.5 flex-1">
                  {plan.features.map(f => {
                    const isHighlight = plan.highlightFeatures?.includes(f)
                    return (
                      <li key={f} className="flex items-center gap-2.5 text-xs">
                        {isHighlight
                          ? <Sparkles className="h-3.5 w-3.5 text-[#674CC4] shrink-0" />
                          : <CheckCircle className="h-3.5 w-3.5 text-[#674CC4] shrink-0" />
                        }
                        <span className={isHighlight ? 'text-white font-medium' : 'text-gray-300'}>{f}</span>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )
          })}
        </div>
        <p className="mt-8 text-center text-sm text-gray-600">
          ¿Más de 10,000 mensajes/mes?{' '}
          <Link to="/register" className="text-indigo-400 hover:text-indigo-300">Contáctanos para Enterprise</Link>
        </p>
      </div>
    </section>
  )
}
