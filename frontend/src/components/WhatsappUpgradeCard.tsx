import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { MessageCircle, X } from 'lucide-react'
import api from '@/lib/api'
import { formatNumber } from '@/lib/utils'

// Conectar WhatsApp se ofrece como mejora cuando el dueño ya vio clientes
// reales en su página, no antes (docs/specs/2026-10-17-meta-sin-friccion.md).
export const WHATSAPP_UPGRADE_MIN_WEB_CUSTOMERS = 5
const DISMISS_KEY = 'iaradio.whatsappUpgradeDismissed'

function wasDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISS_KEY) === '1'
  } catch {
    return false
  }
}

export default function WhatsappUpgradeCard({ webCustomers }: { webCustomers: number }) {
  const [dismissed, setDismissed] = useState(wasDismissed)
  const { data: connection } = useQuery<{ status: string }>({
    queryKey: ['whatsapp-connection'],
    queryFn: () => api.get('/me/whatsapp-connection').then((r) => r.data),
    enabled: webCustomers >= WHATSAPP_UPGRADE_MIN_WEB_CUSTOMERS && !dismissed,
  })

  if (dismissed || webCustomers < WHATSAPP_UPGRADE_MIN_WEB_CUSTOMERS) return null
  if (!connection || connection.status === 'connected') return null

  const dismiss = () => {
    setDismissed(true)
    try {
      localStorage.setItem(DISMISS_KEY, '1')
    } catch {
      // Sin almacenamiento solo se esconde en esta visita.
    }
  }

  return (
    <div className="flex items-start gap-3 rounded-xl border border-brand-200 bg-brand-50 px-5 py-4 dark:border-brand-800 dark:bg-brand-950/30">
      <MessageCircle className="mt-0.5 h-6 w-6 shrink-0 text-brand-600" />
      <div className="min-w-0 flex-1">
        <p className="text-sm text-foreground">
          <strong>Ya atendiste {formatNumber(webCustomers)} clientes por tu página.</strong> ¿Quieres que el bot
          conteste también en tu WhatsApp?
        </p>
        <Link
          to="/app/settings#whatsapp"
          className="mt-2 inline-flex text-sm font-medium text-brand-700 hover:underline dark:text-brand-300"
        >
          Conectar mi WhatsApp →
        </Link>
      </div>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Cerrar"
        className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}
