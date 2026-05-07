import { useQuery } from '@tanstack/react-query'
import { useSearchParams, Link } from 'react-router-dom'
import api from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { Megaphone, Users, MessageSquare, TrendingUp, CheckCircle, Circle } from 'lucide-react'
import { formatNumber } from '@/lib/utils'
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

  const kpis = [
    {
      label: 'Contactos activos',
      value: data?.contacts_total ?? 0,
      icon: Users,
      color: 'text-blue-500',
      bg: 'bg-blue-50',
    },
    {
      label: 'Campañas activas',
      value: data?.campaigns_active ?? 0,
      icon: Megaphone,
      color: 'text-purple-500',
      bg: 'bg-purple-50',
    },
    {
      label: 'Mensajes este mes',
      value: data?.messages_sent_this_month ?? 0,
      icon: MessageSquare,
      color: 'text-green-500',
      bg: 'bg-green-50',
    },
    {
      label: 'Mensajes restantes',
      value: data?.messages_remaining ?? 0,
      icon: TrendingUp,
      color: 'text-brand-500',
      bg: 'bg-brand-50',
    },
  ]

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 rounded-lg bg-gray-200 animate-pulse" />
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-28 rounded-xl bg-gray-200 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Payment success banner */}
      {paymentSuccess && (
        <div className="flex items-center justify-between rounded-xl border border-green-200 bg-green-50 px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🎉</span>
            <div>
              <p className="text-sm font-semibold text-green-800">¡Pago completado! Bienvenido a AdRadio.</p>
              <p className="text-xs text-green-600">Tu plan ya está activo. Puedes empezar a crear campañas ahora mismo.</p>
            </div>
          </div>
          <button onClick={dismissSuccess} className="text-green-500 hover:text-green-700 text-lg leading-none">×</button>
        </div>
      )}

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Hola, {user?.business_name ?? 'Anunciante'} 👋
        </h1>
        <p className="mt-1 text-gray-500">
          Tu radio publicitaria está{' '}
          <span className="font-medium text-green-600">
            {data?.subscription_status === 'active' ? 'emitiendo' : 'en prueba'}
          </span>
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map(({ label, value, icon: Icon, color, bg }) => (
          <div key={label} className="rounded-xl bg-white p-5 shadow-sm border border-gray-100">
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500">{label}</p>
              <div className={`rounded-lg p-2 ${bg}`}>
                <Icon className={`h-5 w-5 ${color}`} />
              </div>
            </div>
            <p className="mt-3 text-3xl font-bold text-gray-900">{formatNumber(value)}</p>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div className="rounded-xl bg-white p-6 shadow-sm border border-gray-100">
        <h2 className="mb-4 text-base font-semibold text-gray-900">Mensajes enviados (7 días)</h2>
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
        <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-6">
          <h2 className="mb-4 text-base font-semibold text-indigo-900">🚀 Primeros pasos</h2>
          <ol className="space-y-3">
            {[
              {
                done: !!(user?.business_name),
                label: 'Completa los datos de tu negocio',
                desc: 'Nombre, categoría y ciudad para que el bot suene auténtico.',
                to: '/settings',
              },
              {
                done: (data?.contacts_total ?? 0) > 0,
                label: 'Importa tus primeros contactos',
                desc: 'Sube un CSV o agrega clientes uno por uno.',
                to: '/contacts',
              },
              {
                done: false,
                label: 'Sube tu base de conocimiento',
                desc: 'PDFs, menús o listas de precios para que el bot responda con precisión.',
                to: '/knowledge-base',
              },
              {
                done: false,
                label: 'Crea tu primera campaña de radio',
                desc: 'Claude genera el guion + voz + jingle en segundos.',
                to: '/campaigns',
              },
            ].map((step, i) => (
              <li key={i} className="flex items-start gap-3">
                {step.done
                  ? <CheckCircle className="mt-0.5 h-5 w-5 shrink-0 text-green-500" />
                  : <Circle className="mt-0.5 h-5 w-5 shrink-0 text-indigo-300" />}
                <div className="flex-1 min-w-0">
                  <Link
                    to={step.to}
                    className={`text-sm font-medium ${step.done ? 'text-gray-400 line-through' : 'text-indigo-800 hover:underline'}`}
                  >
                    {step.label}
                  </Link>
                  {!step.done && <p className="text-xs text-indigo-600">{step.desc}</p>}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Quick actions */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-brand-100 bg-brand-50 p-5">
          <h3 className="font-semibold text-brand-700">🎙️ Nueva campaña</h3>
          <p className="mt-1 text-sm text-brand-600">
            Claude IA crea el mensaje perfecto para tu negocio en segundos.
          </p>
          <a
            href="/campaigns"
            className="mt-3 inline-flex items-center text-sm font-medium text-brand-600 hover:underline"
          >
            Crear campaña →
          </a>
        </div>
        <div className="rounded-xl border border-green-100 bg-green-50 p-5">
          <h3 className="font-semibold text-green-700">📞 Importar contactos</h3>
          <p className="mt-1 text-sm text-green-600">
            Sube tu lista de clientes en CSV y empieza a emitir hoy mismo.
          </p>
          <a
            href="/contacts"
            className="mt-3 inline-flex items-center text-sm font-medium text-green-600 hover:underline"
          >
            Ir a contactos →
          </a>
        </div>
      </div>
    </div>
  )
}
