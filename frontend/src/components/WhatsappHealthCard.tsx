import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { Activity, AlertTriangle, Clock, PauseCircle } from 'lucide-react'

interface Connection {
  status: string
}

interface Health {
  quality_rating: string | null
  messaging_tier: string | null
  tier_recipient_limit: number | null
  send_throttle_per_hour: number
  warmup_active: boolean
  warmup_recipient_cap: number | null
  warmup_days_remaining: number | null
  recipients_sent_last_24h: number
  effective_recipient_limit: number | null
  active_campaigns_count: number
  paused_campaigns_count: number
}

const RATING_STYLES: Record<string, string> = {
  GREEN: 'bg-green-50 border-green-200 text-green-800',
  YELLOW: 'bg-amber-50 border-amber-200 text-amber-800',
  RED: 'bg-red-50 border-red-200 text-red-800',
}

const RATING_LABELS: Record<string, string> = {
  GREEN: 'Buena',
  YELLOW: 'En riesgo',
  RED: 'Crítica',
  NA: 'Sin datos aún',
}

export default function WhatsappHealthCard() {
  const { data: connection } = useQuery<Connection>({
    queryKey: ['whatsapp-connection'],
    queryFn: () => api.get('/me/whatsapp-connection').then((r) => r.data),
  })

  const isConnected = connection?.status === 'connected'

  const { data: health } = useQuery<Health>({
    queryKey: ['whatsapp-health'],
    queryFn: () => api.get('/me/whatsapp-health').then((r) => r.data),
    enabled: isConnected,
    refetchInterval: 60_000,
  })

  if (!isConnected || !health) return null

  const rating = health.quality_rating ?? 'NA'
  const ratingStyle = RATING_STYLES[rating] ?? 'bg-muted border-border text-muted-foreground'
  const ratingLabel = RATING_LABELS[rating] ?? rating

  const capPct = health.effective_recipient_limit
    ? Math.min(100, Math.round((health.recipients_sent_last_24h / health.effective_recipient_limit) * 100))
    : null

  return (
    <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-5">
      <div className="flex items-center gap-2">
        <Activity className="h-5 w-5 text-brand-500" />
        <h2 className="text-base font-semibold text-foreground">Salud de la cuenta de WhatsApp</h2>
      </div>

      {health.paused_campaigns_count > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-sm text-amber-800">
          <PauseCircle className="h-4 w-4 shrink-0" />
          Tienes {health.paused_campaigns_count} campaña{health.paused_campaigns_count === 1 ? '' : 's'} pausada
          {health.paused_campaigns_count === 1 ? '' : 's'} — revisa Campañas para ver por qué.
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className={`rounded-lg border px-3.5 py-2.5 ${ratingStyle}`}>
          <div className="text-xs font-medium opacity-80">Calidad ante Meta</div>
          <div className="text-sm font-semibold">{ratingLabel}</div>
        </div>
        <div className="rounded-lg border border-border px-3.5 py-2.5">
          <div className="text-xs font-medium text-muted-foreground">Ritmo de envío</div>
          <div className="text-sm font-semibold text-foreground">{health.send_throttle_per_hour} msgs/hora</div>
        </div>
      </div>

      {health.warmup_active && (
        <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3.5 py-2.5 text-sm text-blue-800">
          <Clock className="h-4 w-4 shrink-0 mt-0.5" />
          <div>
            Número en periodo de calentamiento — tope actual de{' '}
            <span className="font-medium">{health.warmup_recipient_cap} destinatarios nuevos/24h</span>.
            {health.warmup_days_remaining != null && (
              <> Faltan ~{Math.ceil(health.warmup_days_remaining)} día{Math.ceil(health.warmup_days_remaining) === 1 ? '' : 's'} para el tope completo.</>
            )}
          </div>
        </div>
      )}

      <div>
        <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
          <span>Destinatarios nuevos usados (últimas 24h)</span>
          <span>
            {health.recipients_sent_last_24h}
            {health.effective_recipient_limit != null ? ` / ${health.effective_recipient_limit}` : ' (sin tope)'}
          </span>
        </div>
        {capPct != null && (
          <div className="h-2 rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full ${capPct >= 90 ? 'bg-red-500' : capPct >= 70 ? 'bg-amber-500' : 'bg-brand-500'}`}
              style={{ width: `${capPct}%` }}
            />
          </div>
        )}
      </div>

      {health.messaging_tier && (
        <p className="text-xs text-muted-foreground">
          Tier de Meta: <span className="font-medium text-foreground">{health.messaging_tier}</span>
          {health.tier_recipient_limit != null && ` (${health.tier_recipient_limit} destinatarios/24h)`}
        </p>
      )}

      {rating === 'RED' && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-800">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Meta marcó tu número con calidad crítica — tus campañas activas se pausaron automáticamente.
        </div>
      )}
    </div>
  )
}
