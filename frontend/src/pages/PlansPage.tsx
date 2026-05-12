import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { CheckCircle, Zap, Sparkles } from 'lucide-react'
import { PLANS_CONFIG, type PlanDefinition } from '@/lib/plans'

interface BackendPlan {
  name: string
  price_mxn: number
  price_usd: number
  messages: number
  days: number
}

export default function PlansPage() {
  const { user } = useAuth()
  const [loading, setLoading] = useState<string | null>(null)
  const [currency, setCurrency] = useState<'MXN' | 'USD'>('MXN')

  // Precios dinámicos desde el backend (fuente de verdad para montos de Stripe)
  const { data: backendPlans } = useQuery<Record<string, BackendPlan>>({
    queryKey: ['plans'],
    queryFn: () => api.get('/plans').then((r) => r.data),
  })

  const handleSubscribe = async (planKey: string) => {
    setLoading(planKey)
    try {
      const { data } = await api.post('/checkout/create-session', { plan: planKey })
      window.location.href = data.checkout_url
    } catch (err: any) {
      alert(err.response?.data?.detail ?? 'Error al iniciar pago')
    } finally {
      setLoading(null)
    }
  }

  const formatPrice = (plan: PlanDefinition) => {
    const bp = backendPlans?.[plan.key]
    const mxn = bp?.price_mxn ?? plan.price_mxn
    const usd = bp?.price_usd ?? plan.price_usd
    if (currency === 'MXN') {
      return new Intl.NumberFormat('es-MX', {
        style: 'currency', currency: 'MXN', maximumFractionDigits: 0,
      }).format(mxn)
    }
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(usd)
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gray-900">Planes IaRadio</h1>
        <p className="mt-2 text-gray-500">
          Sin contratos. Cancela cuando quieras. Cambia de plan en cualquier momento.
        </p>

        {/* Toggle MXN / USD */}
        <div className="mt-4 inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 p-1">
          {(['MXN', 'USD'] as const).map((cur) => (
            <button
              key={cur}
              onClick={() => setCurrency(cur)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                currency === cur ? 'bg-brand-500 text-white shadow' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {cur} $
            </button>
          ))}
        </div>
      </div>

      {/* Plan cards */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
        {PLANS_CONFIG.map((plan) => {
          const isPopular = plan.popular
          const isCurrentPlan = user?.current_plan === plan.key

          return (
            <div
              key={plan.key}
              className={`relative flex flex-col rounded-2xl border p-6 transition-shadow ${
                isPopular
                  ? 'border-brand-500 shadow-xl shadow-brand-100 bg-white'
                  : isCurrentPlan
                  ? 'border-green-400 shadow-lg shadow-green-100 bg-white'
                  : 'border-gray-200 bg-white shadow-sm hover:shadow-md'
              }`}
            >
              {/* Badge */}
              {isPopular && !isCurrentPlan && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 whitespace-nowrap">
                  <span className="inline-flex items-center gap-1 rounded-full bg-brand-500 px-3 py-1 text-xs font-bold text-white">
                    <Zap className="h-3 w-3" /> MÁS POPULAR
                  </span>
                </div>
              )}
              {isCurrentPlan && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 whitespace-nowrap">
                  <span className="inline-flex items-center gap-1 rounded-full bg-green-500 px-3 py-1 text-xs font-bold text-white">
                    ✔ Tu plan actual
                  </span>
                </div>
              )}

              {/* Price block */}
              <div className="mb-3">
                <h3 className="text-lg font-bold text-gray-900">{plan.name}</h3>
                <p className="mt-0.5 text-xs text-gray-400">{plan.tagline}</p>
                <div className="mt-3 flex items-baseline gap-1">
                  <span className="text-3xl font-extrabold text-gray-900">{formatPrice(plan)}</span>
                  <span className="text-gray-400 text-sm">/mes</span>
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  {plan.messages.toLocaleString()} mensajes incluidos
                </p>
              </div>

              {/* Feature list */}
              <ul className="mb-6 flex-1 space-y-2">
                {plan.features.map((feat) => {
                  const isHighlight = plan.highlightFeatures?.includes(feat)
                  return (
                    <li key={feat} className="flex items-start gap-2 text-sm">
                      {isHighlight ? (
                        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
                      ) : (
                        <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
                      )}
                      <span className={isHighlight ? 'font-medium text-gray-800' : 'text-gray-600'}>
                        {feat}
                      </span>
                    </li>
                  )
                })}
              </ul>

              {/* CTA */}
              <button
                id={`plan-cta-${plan.key}`}
                onClick={() => handleSubscribe(plan.key)}
                disabled={loading === plan.key || isCurrentPlan}
                className={`w-full rounded-xl py-2.5 text-sm font-semibold transition-all disabled:opacity-60 ${
                  isCurrentPlan
                    ? 'bg-green-100 text-green-700 cursor-default'
                    : isPopular
                    ? 'bg-brand-500 text-white hover:bg-brand-600 shadow-md'
                    : 'border border-gray-300 text-gray-700 hover:bg-gray-50'
                }`}
              >
                {loading === plan.key
                  ? 'Procesando...'
                  : isCurrentPlan
                  ? 'Plan activo'
                  : `Empezar con ${plan.name}`}
              </button>
            </div>
          )
        })}
      </div>

      {/* Footer strip */}
      <div className="rounded-xl bg-gray-50 border border-gray-200 p-5 text-center text-sm text-gray-500">
        💳 Pago seguro con Stripe &nbsp;·&nbsp; 🔒 Sin contratos &nbsp;·&nbsp; ↩️ Devolución en 7 días
      </div>
    </div>
  )
}
