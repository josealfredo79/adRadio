import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { BarChart3, Clock, TrendingUp } from 'lucide-react'
import SEO from '@/components/SEO'

interface HourData {
  hour: number
  label: string
  count: number
}

interface AnalyticsData {
  hours: HourData[]
  best_window: string
  best_hour: number
}

export default function AnalyticsPage() {
  const { data, isLoading } = useQuery<AnalyticsData>({
    queryKey: ['analytics-optimal'],
    queryFn: () => api.get('/analytics/optimal-send-time').then(r => r.data),
    staleTime: 300_000,
  })

  const maxCount = Math.max(...(data?.hours.map(h => h.count) ?? [0]), 1)

  return (
    <>
      <SEO title="Analíticas" description="Panel de control de IaRadio." noIndex />
      <div className="space-y-8 max-w-4xl">
      <div className="flex items-center gap-3">
        <div className="rounded-xl bg-brand-50 dark:bg-brand-950/30 p-2.5">
          <BarChart3 className="h-5 w-5 text-brand-500 dark:text-brand-400" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Analytics</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">Distribución de mensajes entrantes por hora</p>
        </div>
      </div>

      {isLoading ? (
        <div className="h-80 bg-gray-100 dark:bg-gray-800 animate-pulse rounded-xl" />
      ) : !data ? (
        <p className="text-gray-400 dark:text-gray-500 text-sm">No hay datos suficientes aún.</p>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="rounded-xl bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 p-5 flex items-center gap-4">
              <div className="rounded-lg bg-green-50 dark:bg-green-950/30 p-2.5">
                <TrendingUp className="h-5 w-5 text-green-600 dark:text-green-400" />
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Mejor horario para enviar</p>
                <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{data.best_window}</p>
              </div>
            </div>
            <div className="rounded-xl bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 p-5 flex items-center gap-4">
              <div className="rounded-lg bg-blue-50 dark:bg-blue-950/30 p-2.5">
                <Clock className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Hora pico de actividad</p>
                <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{data.best_hour.toString().padStart(2, '0')}:00</p>
              </div>
            </div>
          </div>

          {/* Chart */}
          <div className="rounded-xl bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 p-6">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-6">Mensajes entrantes por hora</h2>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={data.hours} margin={{ top: 0, right: 8, left: -16, bottom: 0 }}>
                <XAxis dataKey="label" interval={1} tick={{ fontSize: 11, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#9CA3AF' }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip
                  formatter={(value: number) => [value, 'mensajes']}
                  labelFormatter={(label: string) => `Hora ${label}`}
                  contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 13 }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={20}>
                  {data.hours.map((entry) => (
                    <Cell
                      key={entry.hour}
                      fill={entry.count >= maxCount * 0.7 ? '#674CC4' : entry.count > 0 ? '#A78BFA' : '#F3F4F6'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="rounded-xl bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5 text-sm text-gray-500 dark:text-gray-400">
            <p className="font-medium text-gray-700 dark:text-gray-300 mb-1">💡 Cómo usarlo</p>
            <p>Programa tus campañas en el <strong>mejor horario</strong> para maximizar la tasa de apertura. Los colores más oscuros indican mayor actividad de tus clientes.</p>
          </div>
        </>
      )}
    </div>
    </>
  )
}
