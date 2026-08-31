import { X, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import {
  ResponsiveContainer, BarChart, XAxis, YAxis, Tooltip, Bar, Cell, LabelList,
} from 'recharts'
import { Campaign, STATUS_COLORS, STATUS_LABELS } from '../types'

interface AnalyticsModalProps {
  campaign: Campaign
  onClose: () => void
}

// WhatsApp industry benchmarks
const BENCHMARKS = {
  delivery: 95,
  response: 35,
  read: 70,
  coupon: 20,
}

function BenchmarkBadge({ value, benchmark }: { value: number; benchmark: number }) {
  const diff = value - benchmark
  if (diff > 5) return <span className="flex items-center gap-0.5 text-[10px] text-green-500 font-semibold"><TrendingUp className="h-2.5 w-2.5" />+{diff}% vs. promedio</span>
  if (diff < -5) return <span className="flex items-center gap-0.5 text-[10px] text-red-400 font-semibold"><TrendingDown className="h-2.5 w-2.5" />{diff}% vs. promedio</span>
  return <span className="flex items-center gap-0.5 text-[10px] text-gray-400"><Minus className="h-2.5 w-2.5" />Promedio</span>
}

interface CustomTooltipProps {
  active?: boolean
  payload?: { value: number }[]
  label?: string
}

const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-lg border border-border bg-card px-3 py-2 shadow-lg text-xs">
        <p className="font-semibold text-foreground mb-0.5">{label}</p>
        <p className="text-muted-foreground">{payload[0].value.toLocaleString()} mensajes</p>
      </div>
    )
  }
  return null
}

export function AnalyticsModal({ campaign, onClose }: AnalyticsModalProps) {
  const s = campaign.stats
  const sent = s.sent ?? 0
  const delivered = s.delivered ?? 0
  const read = s.read ?? 0
  const replied = s.replied ?? 0
  const coupons = s.coupons_redeemed ?? 0
  const failed = s.failed ?? 0
  const hasCoupon = campaign.ab_test?.has_coupon

  const rate = (num: number, den: number) => (den > 0 ? Math.min(100, Math.round((num / den) * 100)) : 0)
  const deliveryRate = rate(delivered, sent)
  const responseRate = rate(replied, sent)
  const readRate = rate(read, delivered)
  const couponRate = rate(coupons, sent)

  const chartData = [
    { name: 'Enviados', value: sent, fill: '#60a5fa' },
    { name: 'Entregados', value: delivered, fill: '#34d399' },
    { name: 'Leídos', value: read, fill: '#818cf8' },
    { name: 'Respondidos', value: replied, fill: '#f59e0b' },
    { name: 'Fallidos', value: failed, fill: '#f87171' },
    ...(hasCoupon ? [{ name: 'Cupones', value: coupons, fill: '#fb923c' }] : []),
  ]

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 dark:bg-black/80 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-card p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-foreground">{campaign.name}</h3>
            <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[campaign.status] ?? 'bg-muted text-gray-600 dark:bg-gray-800 dark:text-gray-400'}`}>
              {STATUS_LABELS[campaign.status] ?? campaign.status}
            </span>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-gray-600 dark:hover:text-gray-400 transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-5">
          {/* Bar Chart */}
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-2">Distribución de mensajes</p>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} margin={{ top: 16, right: 8, left: -20, bottom: 0 }}>
                <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  <LabelList
                    dataKey="value"
                    position="top"
                    style={{ fontSize: 10, fill: 'currentColor' }}
                    formatter={(v: number) => v > 0 ? v.toLocaleString() : ''}
                  />
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Metric cards */}
          {sent > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-2">Rendimiento vs. benchmark WhatsApp</p>
              <div className={`grid gap-2 ${hasCoupon ? 'grid-cols-2' : 'grid-cols-3'}`}>
                <div className="rounded-lg bg-green-50 dark:bg-green-950/30 p-3 text-center space-y-1">
                  <div className="text-lg font-black text-green-700 dark:text-green-300">{deliveryRate}%</div>
                  <div className="text-[10px] text-green-600 dark:text-green-400 font-medium">Entrega</div>
                  <BenchmarkBadge value={deliveryRate} benchmark={BENCHMARKS.delivery} />
                </div>
                <div className="rounded-lg bg-violet-50 dark:bg-violet-950/30 p-3 text-center space-y-1">
                  <div className="text-lg font-black text-violet-700 dark:text-violet-300">{readRate}%</div>
                  <div className="text-[10px] text-violet-600 dark:text-violet-400 font-medium">Lectura</div>
                  <BenchmarkBadge value={readRate} benchmark={BENCHMARKS.read} />
                </div>
                <div className="rounded-lg bg-brand-50 dark:bg-brand-950/30 p-3 text-center space-y-1">
                  <div className="text-lg font-black text-brand-700 dark:text-brand-300">{responseRate}%</div>
                  <div className="text-[10px] text-brand-600 dark:text-brand-400 font-medium">Respuesta</div>
                  <BenchmarkBadge value={responseRate} benchmark={BENCHMARKS.response} />
                </div>
                {hasCoupon && (
                  <div className="rounded-lg bg-orange-50 dark:bg-orange-950/30 p-3 text-center space-y-1">
                    <div className="text-lg font-black text-orange-700 dark:text-orange-300">{couponRate}%</div>
                    <div className="text-[10px] text-orange-600 dark:text-orange-400 font-medium">Cupones</div>
                    <BenchmarkBadge value={couponRate} benchmark={BENCHMARKS.coupon} />
                  </div>
                )}
              </div>
              <p className="mt-2 text-[10px] text-muted-foreground/60 text-center">
                Benchmark: entrega ~{BENCHMARKS.delivery}% · lectura ~{BENCHMARKS.read}% · respuesta ~{BENCHMARKS.response}% (promedio WhatsApp Business)
              </p>
            </div>
          )}

          {/* Schedule info */}
          {campaign.schedule?.start_date && (
            <p className="text-xs text-muted-foreground border-t border-border pt-3">
              📅 Programada para {new Date(campaign.schedule.start_date).toLocaleString('es-MX', { dateStyle: 'long', timeStyle: 'short' })}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
