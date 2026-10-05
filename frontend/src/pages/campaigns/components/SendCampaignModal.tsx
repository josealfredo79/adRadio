import { useQuery } from '@tanstack/react-query'
import { X, Globe, MessageCircle, Loader2, Send, Info } from 'lucide-react'
import api from '@/lib/api'
import { Campaign } from '../types'

// Antes de enviar: a cuántos clientes les llega gratis como notificación web
// (los que las activaron en su portal) y a cuántos por WhatsApp, con lo que
// cobraría Meta. Se puede mandar a todos o solo por web (gratis).

interface Reach {
  total: number
  web: number
  whatsapp: number
  whatsapp_cost_mxn: number
  web_supported: boolean
}

interface SendCampaignModalProps {
  campaign: Campaign
  sending: boolean
  onSend: (webOnly: boolean) => void
  onClose: () => void
}

const pesos = (n: number) => n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN' })
const clientes = (n: number) => `${n.toLocaleString('es-MX')} ${n === 1 ? 'cliente' : 'clientes'}`

export function SendCampaignModal({ campaign, sending, onSend, onClose }: SendCampaignModalProps) {
  const { data: reach, isLoading, isError } = useQuery<Reach>({
    queryKey: ['campaign-reach', campaign.id],
    queryFn: () => api.get(`/campaigns/${campaign.id}/reach`).then((r) => r.data),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 dark:bg-black/80 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-card p-6 shadow-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Enviar campaña</h2>
            <p className="text-sm text-muted-foreground">{campaign.name}</p>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1 text-muted-foreground hover:bg-muted">
            <X className="h-5 w-5" />
          </button>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
        ) : isError || !reach ? (
          <p className="py-4 text-sm text-muted-foreground">No pudimos calcular a quién le llega. Puedes enviarla de todos modos.</p>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-foreground">Le llegará a <strong>{clientes(reach.total)}</strong>:</p>
            <div className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 dark:border-emerald-900 dark:bg-emerald-950/30">
              <Globe className="h-5 w-5 shrink-0 text-emerald-600" />
              <p className="text-sm text-foreground">
                <strong>{clientes(reach.web)}</strong> por notificación web — <strong className="text-emerald-700 dark:text-emerald-400">gratis</strong>
              </p>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-border bg-muted/40 px-4 py-3">
              <MessageCircle className="h-5 w-5 shrink-0 text-green-600" />
              <p className="text-sm text-foreground">
                <strong>{clientes(reach.whatsapp)}</strong> por WhatsApp
                {reach.whatsapp > 0 && <> — Meta cobra hasta <strong>≈ {pesos(reach.whatsapp_cost_mxn)}</strong></>}
              </p>
            </div>
            {!reach.web_supported ? (
              <p className="flex gap-2 text-xs text-muted-foreground">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Las Voces del Barrio van como nota de voz, así que solo se mandan por WhatsApp.
              </p>
            ) : reach.web < reach.total && (
              <p className="flex gap-2 text-xs text-muted-foreground">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Entre más clientes activen las notificaciones en su portal, más campañas te salen gratis.
              </p>
            )}
          </div>
        )}

        <div className="mt-6 flex flex-col gap-2">
          {reach?.web_supported && reach.web > 0 && reach.whatsapp > 0 && (
            <button
              onClick={() => onSend(true)}
              disabled={sending}
              className="flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
            >
              <Globe className="h-4 w-4" /> Solo por web — gratis ({clientes(reach.web)})
            </button>
          )}
          <button
            onClick={() => onSend(false)}
            disabled={sending || reach?.total === 0}
            className={`flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold disabled:opacity-60 ${
              reach?.web_supported && reach.web > 0 && reach.whatsapp > 0
                ? 'border border-border text-foreground hover:bg-muted'
                : 'bg-emerald-600 text-white hover:bg-emerald-700'
            }`}
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {reach ? `Enviar a todos (${clientes(reach.total)})` : 'Enviar'}
          </button>
        </div>
      </div>
    </div>
  )
}
