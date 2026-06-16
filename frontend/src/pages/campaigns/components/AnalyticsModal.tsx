import { X } from 'lucide-react'
import { ResponsiveContainer, BarChart, XAxis, YAxis, Tooltip, Bar, Cell } from 'recharts'
import { Campaign, STATUS_COLORS, STATUS_LABELS } from '../types'

interface AnalyticsModalProps {
  campaign: Campaign
  onClose: () => void
}

export function AnalyticsModal({ campaign, onClose }: AnalyticsModalProps) {
  const s = campaign.stats
  const sent = s.sent ?? 0
  const chartData = [
    { name: 'Enviados', value: sent, fill: '#60a5fa' },
    { name: 'Entregados', value: s.delivered ?? 0, fill: '#34d399' },
    { name: 'Leídos', value: s.read ?? 0, fill: '#818cf8' },
    { name: 'Respondidos', value: s.replied ?? 0, fill: '#f59e0b' },
    { name: 'Fallidos', value: s.failed ?? 0, fill: '#f87171' },
    { name: 'Cupones', value: s.coupons_redeemed ?? 0, fill: '#fb923c' },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 dark:bg-black/80 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-card p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-foreground">{campaign.name}</h3>
            <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[campaign.status] ?? 'bg-muted text-gray-600 dark:bg-gray-800 dark:text-gray-400'}`}>
              {STATUS_LABELS[campaign.status] ?? campaign.status}
            </span>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-gray-600 dark:hover:text-gray-400">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip formatter={(v: number) => [v.toLocaleString(), '']} labelStyle={{ fontWeight: 600 }} />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {chartData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          {sent > 0 && (
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-lg bg-green-50 dark:bg-green-950/30 p-2 text-center">
                <div className="font-semibold text-green-700 dark:text-green-300">{Math.round(((s.delivered ?? 0) / sent) * 100)}%</div>
                <div className="text-xs text-green-600">Entrega</div>
              </div>
              <div className="rounded-lg bg-brand-50 dark:bg-brand-950/30 p-2 text-center">
                <div className="font-semibold text-brand-700 dark:text-brand-300">{Math.round(((s.replied ?? 0) / sent) * 100)}%</div>
                <div className="text-xs text-brand-600 dark:text-brand-400">Respuesta</div>
              </div>
            </div>
          )}
        </div>

        {campaign.schedule?.start_date && (
          <p className="mt-4 text-xs text-muted-foreground">
            Programada para {new Date(campaign.schedule.start_date).toLocaleString('es-MX', { dateStyle: 'long', timeStyle: 'short' })}
          </p>
        )}
      </div>
    </div>
  )
}
