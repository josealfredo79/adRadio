import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { CheckCircle, Zap, Sparkles } from 'lucide-react'
import { PLANS_CONFIG, type PlanDefinition } from '@/lib/plans'
import SEO from '@/components/SEO'

interface BackendPlan {
  name: string
  price_mxn: number
  price_usd: number
  messages: number
  days: number
}

export default function PlansPage() {
  const { user } = useAuth()
  const { toast } = useToast()
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
    } catch (err: unknown) {
      toast({ title: 'Error', description: getApiError(err, 'Error al iniciar pago'), variant: 'error' })
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
    <>
      <SEO title="Planes" description="Panel de control de IaRadio." noIndex />
      <div className="space-y-8">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Planes IaRadio</h1>
        <p className="mt-2 text-gray-500 dark:text-gray-400">
          Sin contratos. Cancela cuando quieras. Cambia de plan en cualquier momento.
        </p>

        {/* Toggle MXN / USD */}
        <div className="mt-4 inline-flex items-center gap-1 rounded-full border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 p-1">
          {(['MXN', 'USD'] as const).map((cur) => (
            <button
              key={cur}
              onClick={() => setCurrency(cur)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                currency === cur ? 'bg-brand-500 dark:bg-brand-600 text-white shadow' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
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
                  ? 'border-brand-500 shadow-xl shadow-brand-100 bg-white dark:bg-gray-950'
                  : isCurrentPlan
                  ? 'border-green-400 shadow-lg shadow-green-100 bg-white dark:bg-gray-950'
                  : 'border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shadow-sm hover:shadow-md'
              }`}
            >
              {/* Badge */}
              {isPopular && !isCurrentPlan && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 whitespace-nowrap">
                  <span className="inline-flex items-center gap-1 rounded-full bg-brand-500 dark:bg-brand-600 px-3 py-1 text-xs font-bold text-white">
                    <Zap className="h-3 w-3" /> MÁS POPULAR
                  </span>
                </div>
              )}
              {isCurrentPlan && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 whitespace-nowrap">
                  <span className="inline-flex items-center gap-1 rounded-full bg-green-500 dark:bg-green-600 px-3 py-1 text-xs font-bold text-white">
                    ✔ Tu plan actual
                  </span>
                </div>
              )}

              {/* Price block */}
              <div className="mb-3">
                <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">{plan.name}</h3>
                <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">{plan.tagline}</p>
                <div className="mt-3 flex items-baseline gap-1">
                  <span className="text-3xl font-extrabold text-gray-900 dark:text-gray-100">{formatPrice(plan)}</span>
                  <span className="text-gray-400 dark:text-gray-500 text-sm">/mes</span>
                </div>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
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
                        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-brand-500 dark:text-brand-400" />
                      ) : (
                        <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
                      )}
                      <span className={isHighlight ? 'font-medium text-gray-800 dark:text-gray-200' : 'text-gray-600 dark:text-gray-400'}>
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
                    ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 cursor-default'
                    : isPopular
                    ? 'bg-brand-500 dark:bg-brand-600 text-white hover:bg-brand-600 dark:hover:bg-brand-500 shadow-md'
                    : 'border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-900'
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
      <div className="rounded-xl bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5 text-center text-sm text-gray-500 dark:text-gray-400">
        💳 Pago seguro con Stripe &nbsp;·&nbsp; 🔒 Sin contratos &nbsp;·&nbsp; ↩️ Devolución en 7 días
      </div>
    </div>
    </>
  )
}
