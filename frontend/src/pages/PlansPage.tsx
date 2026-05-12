import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { CheckCircle, Zap } from 'lucide-react'

interface Plan {
  name: string
  price_mxn: number
  price_usd: number
  messages: number
  days: number
}

const PLAN_FEATURES: Record<string, string[]> = {
  starter: ['200 mensajes/mes', 'Bot IA básico', 'Importar CSV', 'Campañas manuales'],
  growth: [
    '500 mensajes/mes',
    'Bot IA básico',
    'Importar CSV',
    'Campañas manuales',
    'Cupones QR',
    'Métricas básicas',
  ],
  pro: [
    '1,000 mensajes/mes',
    'Bot IA con RAG',
    'Claude genera contenido',
    'Flyers con IA',
    'Métricas avanzadas',
    'Cupones QR',
  ],
  business: [
    '3,000 mensajes/mes',
    'Todo del plan Pro',
    'A/B testing',
    'Sugerencias de leads',
    'Soporte prioritario',
  ],
  enterprise: [
    '10,000 mensajes/mes',
    'Todo del plan Business',
    'Multi-número',
    'White-label',
    'API acceso',
    'Gerente de cuenta dedicado',
  ],
}

export default function PlansPage() {
  const { user } = useAuth()
  const [loading, setLoading] = useState<string | null>(null)
  const [currency, setCurrency] = useState<'MXN' | 'USD'>('MXN')

  const { data: plans } = useQuery<Record<string, Plan>>({
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

  const formatPrice = (plan: Plan) => {
    if (currency === 'MXN') {
      return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 }).format(plan.price_mxn)
    }
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(plan.price_usd)
  }

  const planOrder = ['starter', 'growth', 'pro', 'business', 'enterprise']

  return (
    <div className="space-y-8">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gray-900">Planes IaRadio</h1>
        <p className="mt-2 text-gray-500">
          Elige el plan que mejor se adapte a tu negocio. Sin contratos, cancela cuando quieras.
        </p>

        {/* Toggle MXN / USD */}
        <div className="mt-4 inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 p-1">
          <button
            onClick={() => setCurrency('MXN')}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              currency === 'MXN' ? 'bg-brand-500 text-white shadow' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            MXN $
          </button>
          <button
            onClick={() => setCurrency('USD')}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              currency === 'USD' ? 'bg-brand-500 text-white shadow' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            USD $
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-4">
        {planOrder.map((key) => {
          const plan = plans?.[key]
          if (!plan) return null
          const isGrowth = key === 'growth'
          const features = PLAN_FEATURES[key] ?? []
          const isCurrentPlan = user?.current_plan === key

          return (
            <div
              key={key}
              className={`relative rounded-2xl border p-6 ${
                isGrowth
                  ? 'border-brand-500 shadow-xl shadow-brand-100 bg-white'
                  : isCurrentPlan
                  ? 'border-green-400 shadow-lg shadow-green-100 bg-white'
                  : 'border-gray-200 bg-white shadow-sm'
              }`}
            >
              {isGrowth && !isCurrentPlan && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                  <span className="inline-flex items-center gap-1 rounded-full bg-brand-500 px-3 py-1 text-xs font-bold text-white">
                    <Zap className="h-3 w-3" /> MÁS POPULAR
                  </span>
                </div>
              )}
              {isCurrentPlan && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                  <span className="inline-flex items-center gap-1 rounded-full bg-green-500 px-3 py-1 text-xs font-bold text-white">
                    ✔ Tu plan actual
                  </span>
                </div>
              )}

              <div className="mb-4">
                <h3 className="text-lg font-bold text-gray-900">{plan.name}</h3>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-4xl font-bold text-gray-900">
                    {formatPrice(plan)}
                  </span>
                  <span className="text-gray-500">/mes</span>
                </div>
                <p className="mt-1 text-sm text-gray-500">{plan.messages.toLocaleString()} mensajes</p>
              </div>

              <ul className="mb-6 space-y-2">
                {features.map((feat) => (
                  <li key={feat} className="flex items-start gap-2 text-sm text-gray-600">
                    <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
                    {feat}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => handleSubscribe(key)}
                disabled={loading === key || isCurrentPlan}
                className={`w-full rounded-xl py-2.5 text-sm font-medium transition-colors ${
                  isCurrentPlan
                    ? 'bg-green-100 text-green-700 cursor-default'
                    : isGrowth
                    ? 'bg-brand-500 text-white hover:bg-brand-600 shadow'
                    : 'border border-gray-300 text-gray-700 hover:bg-gray-50'
                } disabled:opacity-60`}
              >
                {loading === key ? 'Procesando...' : isCurrentPlan ? 'Plan activo' : 'Suscribirme'}
              </button>
            </div>
          )
        })}
      </div>

      <div className="rounded-xl bg-gray-50 border border-gray-200 p-6 text-center">
        <p className="text-sm text-gray-600">
          💳 Pago seguro con Stripe · 🔒 Sin contratos · ↩️ Garantía de devolución 7 días
        </p>
      </div>
    </div>
  )
}

