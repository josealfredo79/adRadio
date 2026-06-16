import { Megaphone, Play, Pause, Trash2, BarChart2, Loader2 } from 'lucide-react'
import { ResponsiveContainer, BarChart, XAxis, YAxis, Tooltip, Bar, Cell } from 'recharts'
import { Campaign, STATUS_COLORS, STATUS_LABELS, MODE_BADGE } from '../types'

interface CampaignCardProps {
  campaign: Campaign
  onViewAnalytics: (id: string) => void
  onViewVocesDetail: (id: string) => void
  onPause: (id: string) => void
  onResume: (id: string) => void
  onDelete: (id: string) => void
  isPausePending: boolean
  isResumePending: boolean
}

export function CampaignCard({
  campaign,
  onViewAnalytics,
  onViewVocesDetail,
  onPause,
  onResume,
  onDelete,
  isPausePending,
  isResumePending,
}: CampaignCardProps) {
  const hasSentMessages = (campaign.stats.sent ?? 0) > 0

  const handleConfirmDelete = () => {
    if (window.confirm('¿Eliminar esta campaña?')) {
      onDelete(campaign.id)
    }
  }

  return (
    <div className="rounded-xl bg-card p-5 shadow-sm border border-border">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-foreground truncate">{campaign.name}</h3>
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[campaign.status] ?? 'bg-muted text-gray-600 dark:bg-gray-800 dark:text-gray-400'}`}>
              {STATUS_LABELS[campaign.status] ?? campaign.status}
            </span>
            {campaign.ab_test?.campaign_mode && campaign.ab_test.campaign_mode !== 'regular' && (
              <span className="rounded-full bg-purple-100 dark:bg-purple-900/50 px-2.5 py-0.5 text-xs font-medium text-purple-600 dark:text-purple-300">
                {MODE_BADGE[campaign.ab_test.campaign_mode]}
              </span>
            )}
            {campaign.ab_test?.has_coupon && (
              <span className="rounded-full bg-amber-100 dark:bg-amber-900/50 px-2.5 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-300">
                🎫 Con cupón
              </span>
            )}
          </div>
          <p className="mt-1.5 text-sm text-muted-foreground line-clamp-2">{campaign.message_text}</p>
          {campaign.ab_test?.audio_url && (
            <div className="mt-3">
              <audio controls src={campaign.ab_test.audio_url} className="h-8 w-full max-w-md rounded-lg" />
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span>📤 {campaign.stats.sent ?? 0} enviados</span>
            <span>✅ {campaign.stats.delivered ?? 0} entregados</span>
            <span>💬 {campaign.stats.replied ?? 0} respondidos</span>
            <span>🎫 {campaign.stats.coupons_redeemed ?? 0} canjeados</span>
            {campaign.message_counts && Object.keys(campaign.message_counts).length > 0 && (
              <span title="Estado real de entrega por contacto" className="flex gap-2 ml-2 border-l border-border pl-2">
                {campaign.message_counts.sent > 0 && <span className="text-blue-500">📤{campaign.message_counts.sent}</span>}
                {campaign.message_counts.delivered > 0 && <span className="text-green-500">✅{campaign.message_counts.delivered}</span>}
                {campaign.message_counts.read > 0 && <span className="text-violet-500">👁️{campaign.message_counts.read}</span>}
                {campaign.message_counts.failed > 0 && <span className="text-red-500">❌{campaign.message_counts.failed}</span>}
                {campaign.message_counts.queued > 0 && <span className="text-amber-500">⏳{campaign.message_counts.queued}</span>}
              </span>
            )}
          </div>
          {hasSentMessages && (
            <div className="mt-3 flex flex-wrap items-center gap-4">
              {/* Delivery rate */}
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground whitespace-nowrap">Entrega</span>
                <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-green-400 dark:bg-green-500 transition-all"
                    style={{ width: `${Math.min(100, Math.round(((campaign.stats.delivered ?? 0) / campaign.stats.sent) * 100))}%` }}
                  />
                </div>
                <span className="text-[10px] font-semibold text-green-600 dark:text-green-400">
                  {Math.round(((campaign.stats.delivered ?? 0) / campaign.stats.sent) * 100)}%
                </span>
              </div>
              {/* Response rate */}
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground whitespace-nowrap">Respuesta</span>
                <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-brand-50 dark:bg-brand-400 transition-all"
                    style={{ width: `${Math.min(100, Math.round(((campaign.stats.replied ?? 0) / campaign.stats.sent) * 100))}%` }}
                  />
                </div>
                <span className="text-[10px] font-semibold text-brand-600 dark:text-brand-400">
                  {Math.round(((campaign.stats.replied ?? 0) / campaign.stats.sent) * 100)}%
                </span>
              </div>
            </div>
          )}
          {/* A/B Test Results */}
          {campaign.ab_test?.enabled && (
            <div className="mt-4 border-t border-purple-100 dark:border-purple-800 pt-3">
              <p className="text-xs font-semibold text-purple-700 dark:text-purple-300 mb-2">🔬 Prueba A/B</p>
              {(() => {
                const variants = campaign.ab_test.variants || []
                const statsA = campaign.ab_test.stats_a || { sent: 0, replied: 0 }
                const statsB = campaign.ab_test.stats_b || { sent: 0, replied: 0 }
                const statsC = campaign.ab_test.stats_c || { sent: 0, replied: 0 }
                const allStats = [statsA, statsB]
                if (statsC.sent > 0) allStats.push(statsC)
                const chartData = allStats.map((s: { sent: number; replied: number }, i: number) => {
                  const label = String.fromCharCode(65 + i)
                  const responseRate = s.sent > 0 ? Math.round((s.replied / s.sent) * 100) : 0
                  return {
                    name: `Variante ${label}`,
                    sent: s.sent ?? 0,
                    rate: responseRate,
                    fill: i === 0 ? '#a855f7' : i === 1 ? '#6366f1' : '#ec4899',
                  }
                })
                const maxRate = Math.max(...chartData.map((d) => d.rate), 0)
                return (
                  <div className="space-y-2">
                    <div className="h-24">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                          <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                          <YAxis tick={{ fontSize: 10 }} unit="%" domain={[0, 'auto']} />
                          <Tooltip formatter={(v: number, name: string) => [name === 'rate' ? `${v}%` : v, name === 'rate' ? 'Respuesta' : 'Enviados']} />
                          <Bar dataKey="rate" radius={[4, 4, 0, 0]} fill="#a855f7">
                            {chartData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="flex gap-2 flex-wrap">
                      {chartData.map((d) => (
                        <div key={d.name} className="flex items-center gap-1.5 text-[11px] text-gray-600 dark:text-gray-400 bg-purple-50 dark:bg-purple-950/30 rounded-lg px-2 py-1">
                          <span className="w-2 h-2 rounded-full" style={{ background: d.fill }} />
                          {d.name}: {d.rate}% ({d.sent} enviados)
                          {d.rate === maxRate && d.rate > 0 && (
                            <span className="text-amber-600 font-bold ml-1">🏆</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })()}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 ml-4 shrink-0 flex-wrap">
          <button onClick={() => onViewAnalytics(campaign.id)}
            className="rounded-lg border border-border p-1.5 text-muted-foreground hover:bg-muted transition-colors shrink-0">
            <BarChart2 className="h-3.5 w-3.5" />
          </button>
          {campaign.type === 'voces' && (
            <button onClick={() => onViewVocesDetail(campaign.id)}
              className="rounded-lg border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-950/30 p-1.5 text-purple-600 dark:text-purple-300 hover:bg-purple-100 transition-colors shrink-0">
              <Megaphone className="h-3.5 w-3.5" />
            </button>
          )}
          {campaign.status === 'running' && (
            <button onClick={() => onPause(campaign.id)}
              disabled={isPausePending}
              className="rounded-lg border border-yellow-200 bg-yellow-50 dark:bg-yellow-950/30 p-1.5 text-yellow-600 dark:text-yellow-300 hover:bg-yellow-100 shrink-0 disabled:opacity-50">
              {isPausePending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Pause className="h-3.5 w-3.5" />}
            </button>
          )}
          {(campaign.status === 'paused' || campaign.status === 'draft' || campaign.status === 'scheduled') && (
            <button onClick={() => onResume(campaign.id)}
              disabled={isResumePending}
              title={campaign.status === 'draft' ? "Enviar campaña ahora" : campaign.status === 'scheduled' ? "Forzar envío ahora" : "Reanudar campaña"}
              className="rounded-lg border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/30 p-1.5 text-green-600 dark:text-green-300 hover:bg-green-100 transition-colors shrink-0 disabled:opacity-50">
              {isResumePending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            </button>
          )}
          <button onClick={handleConfirmDelete}
            className="text-muted-foreground hover:text-red-500 dark:hover:text-red-400 transition-colors shrink-0">
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
