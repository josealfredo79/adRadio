import { useQuery } from '@tanstack/react-query'
import { useSearchParams, Link } from 'react-router-dom'
import { useState } from 'react'
import api from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { Megaphone, Users, MessageSquare, TrendingUp, CheckCircle, Circle, ShoppingBag } from 'lucide-react'
import { formatNumber } from '@/lib/utils'
import OnboardingWizard from '@/components/OnboardingWizard'
import SEO from '@/components/SEO'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

interface DashboardData {
  contacts_total: number
  campaigns_active: number
  messages_sent_this_month: number
  messages_remaining: number
  plan: string
  subscription_status: string
  orders_confirmed: number
  orders_pending: number
}

interface ChartPoint {
  day: string
  mensajes: number
  date: string
}

const DAYS_ES: Record<string, string> = {
  Mon: 'Lun', Tue: 'Mar', Wed: 'Mié', Thu: 'Jue', Fri: 'Vie', Sat: 'Sáb', Sun: 'Dom',
}

export default function DashboardPage() {
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const paymentSuccess = searchParams.get('success') === '1'
  const [onboardingDismissed, setOnboardingDismissed] = useState(false)

  // Remove ?success param from URL after showing the banner
  const dismissSuccess = () => {
    searchParams.delete('success')
    setSearchParams(searchParams, { replace: true })
  }
  const { data, isLoading } = useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: () => api.get('/dashboard').then((r) => r.data),
    staleTime: 1000 * 60 * 5,
  })
  const { data: chartData } = useQuery<ChartPoint[]>({
    queryKey: ['dashboard-chart'],
    queryFn: () => api.get('/dashboard/chart').then((r) => r.data),
    staleTime: 1000 * 60 * 5,
  })
  const { data: kbFiles } = useQuery<{ id: string }[]>({
    queryKey: ['knowledge-base'],
    queryFn: () => api.get('/knowledge-base').then((r) => r.data),
    staleTime: 1000 * 60 * 5,
  })

  const showOnboarding = !onboardingDismissed
    && !isLoading
    && (kbFiles?.length ?? 0) === 0
    && (data?.contacts_total ?? 0) === 0
    && (data?.campaigns_active ?? 0) === 0

  const kpis = [
    {
      label: 'Contactos activos',
      value: data?.contacts_total ?? 0,
      icon: Users,
      color: 'text-blue-500 dark:text-blue-400',
      bg: 'bg-blue-50 dark:bg-blue-950/30',
    },
    {
      label: 'Campañas activas',
      value: data?.campaigns_active ?? 0,
      icon: Megaphone,
      color: 'text-purple-500 dark:text-purple-400',
      bg: 'bg-purple-50 dark:bg-purple-950/30',
    },
    {
      label: 'Mensajes este mes',
      value: data?.messages_sent_this_month ?? 0,
      icon: MessageSquare,
      color: 'text-green-500 dark:text-green-400',
      bg: 'bg-green-50 dark:bg-green-950/30',
    },
    {
      label: 'Mensajes restantes',
      value: data?.messages_remaining ?? 0,
      icon: TrendingUp,
      color: 'text-brand-500 dark:text-brand-400',
      bg: 'bg-brand-50 dark:bg-brand-950/30',
    },
  ]

  if (isLoading) {
    return (
      <>
        <SEO title="Dashboard" description="Panel de control de IaRadio." noIndex />
        <div className="space-y-6">
        <div className="h-8 w-48 rounded-lg bg-muted animate-pulse" />
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-28 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      </div>
      </>
    )
  }

  return (
    <>
      <SEO title="Dashboard" description="Panel de control de IaRadio." noIndex />
      <div className="space-y-8">
      {showOnboarding && <OnboardingWizard onClose={() => setOnboardingDismissed(true)} />}
      {/* Payment success banner */}
      {paymentSuccess && (
        <div className="flex items-center justify-between rounded-xl border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/30 px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🎉</span>
            <div>
              <p className="text-sm font-semibold text-green-800 dark:text-green-200">¡Pago completado! Bienvenido a IaRadio.</p>
              <p className="text-xs text-green-600 dark:text-green-300">Tu plan ya está activo. Puedes empezar a crear campañas ahora mismo.</p>
            </div>
          </div>
          <button onClick={dismissSuccess} className="text-green-500 hover:text-green-700 dark:text-green-400 dark:hover:text-green-300 text-lg leading-none">×</button>
        </div>
      )}

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">
          Hola, {user?.business_name ?? 'Anunciante'} 👋
        </h1>
        <p className="mt-1 text-muted-foreground">
          Tu radio publicitaria está{' '}
          <span className="font-medium text-green-600 dark:text-green-400">
            {data?.subscription_status === 'active' ? 'emitiendo' : 'en prueba'}
          </span>
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map(({ label, value, icon: Icon, color, bg }) => (
          <div key={label} className="rounded-xl bg-card p-5 shadow-sm border border-border">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">{label}</p>
              <div className={`rounded-lg p-2 ${bg}`}>
                <Icon className={`h-5 w-5 ${color}`} />
              </div>
            </div>
            <p className="mt-3 text-3xl font-bold text-foreground">{formatNumber(value)}</p>
          </div>
        ))}
      </div>

      {/* Orders bot summary */}
      <Link
        to="/app/orders"
        className="flex items-center justify-between rounded-xl border border-brand-100 dark:border-brand-800 bg-brand-50 dark:bg-brand-950/30 px-6 py-4 hover:border-brand-300 dark:hover:border-brand-600 hover:bg-brand-100 dark:hover:bg-brand-900/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-brand-500 p-2">
            <ShoppingBag className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-brand-900 dark:text-brand-100">Pedidos del bot de WhatsApp</p>
            <p className="text-xs text-brand-600 dark:text-brand-400 mt-0.5">
              {data?.orders_confirmed ?? 0} confirmados &middot; {data?.orders_pending ?? 0} en proceso
            </p>
          </div>
        </div>
        <span className="text-sm font-medium text-brand-600 dark:text-brand-400">Ver todos &rarr;</span>
      </Link>

      {/* Chart */}
      <div className="rounded-xl bg-card p-6 shadow-sm border border-border">
        <h2 className="mb-4 text-base font-semibold text-foreground">Mensajes enviados (7 días)</h2>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={(chartData ?? []).map((p) => ({ ...p, day: DAYS_ES[p.day] ?? p.day }))}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="day" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="mensajes"
              stroke="#6366f1"
              strokeWidth={2}
              dot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Primeros pasos — shown while user hasn't sent any campaign */}
      {(data?.campaigns_active ?? 0) === 0 && (data?.messages_sent_this_month ?? 0) === 0 && (
        <div className="rounded-xl border border-indigo-100 dark:border-indigo-800/50 bg-indigo-50 dark:bg-indigo-950/30 p-6">
          <h2 className="mb-4 text-base font-semibold text-indigo-900 dark:text-indigo-200">🚀 Primeros pasos</h2>
          <ol className="space-y-3">
            {[
              {
                done: !!(user?.business_name),
                label: 'Completa los datos de tu negocio',
                desc: 'Nombre, categoría y ciudad para que el bot suene auténtico.',
                to: '/app/settings',
              },
              {
                done: (data?.contacts_total ?? 0) > 0,
                label: 'Importa tus primeros contactos',
                desc: 'Sube un CSV o agrega clientes uno por uno.',
                to: '/app/contacts',
              },
              {
                done: (kbFiles?.length ?? 0) > 0,
                label: 'Sube tu base de conocimiento',
                desc: 'PDFs, menús o listas de precios para que el bot responda con precisión.',
                to: '/app/knowledge-base',
              },
              {
                done: false,
                label: 'Crea tu primera campaña de radio',
                desc: 'Claude genera el guion + voz + jingle en segundos.',
                to: '/app/campaigns',
              },
            ].map((step, i) => (
              <li key={i} className="flex items-start gap-3">
                {step.done
                  ? <CheckCircle className="mt-0.5 h-5 w-5 shrink-0 text-green-500 dark:text-green-400" />
                  : <Circle className="mt-0.5 h-5 w-5 shrink-0 text-indigo-300 dark:text-indigo-400" />}
                <div className="flex-1 min-w-0">
                  <Link
                    to={step.to}
                    className={`text-sm font-medium ${step.done ? 'text-muted-foreground line-through' : 'text-indigo-800 dark:text-indigo-300 hover:underline'}`}
                  >
                    {step.label}
                  </Link>
                  {!step.done && <p className="text-xs text-indigo-600 dark:text-indigo-400">{step.desc}</p>}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Quick actions */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-brand-100 dark:border-brand-800 bg-brand-50 dark:bg-brand-950/30 p-5">
          <h3 className="font-semibold text-brand-700 dark:text-brand-300">🎙️ Nueva campaña</h3>
          <p className="mt-1 text-sm text-brand-600 dark:text-brand-400">
            Claude IA crea el mensaje perfecto para tu negocio en segundos.
          </p>
          <a
            href="/app/campaigns"
            className="mt-3 inline-flex items-center text-sm font-medium text-brand-600 dark:text-brand-400 hover:underline"
          >
            Crear campaña →
          </a>
        </div>
        <div className="rounded-xl border border-green-100 dark:border-green-800 bg-green-50 dark:bg-green-950/30 p-5">
          <h3 className="font-semibold text-green-700 dark:text-green-300">📞 Importar contactos</h3>
          <p className="mt-1 text-sm text-green-600 dark:text-green-400">
            Sube tu lista de clientes en CSV y empieza a emitir hoy mismo.
          </p>
          <a
            href="/app/contacts"
            className="mt-3 inline-flex items-center text-sm font-medium text-green-600 dark:text-green-400 hover:underline"
          >
            Ir a contactos →
          </a>
        </div>
      </div>
    </div>
    </>
  )
}
