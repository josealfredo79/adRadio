import { useEffect, useState } from 'react'
import { BellRing } from 'lucide-react'
import InlineJoin from '@/components/InlineJoin'
import type { ChatPalette } from '@/lib/chatLook'
import { detectNotifyState } from '@/lib/webPushClient'

// Visitante sin registrar que vio un producto: "🔔 Avísame". Los avisos se
// guardan por cliente, así que primero se registra con su WhatsApp y código
// (InlineJoin, el mismo registro del chat) y luego el chat le ofrece activarlos
// (ChatNotifyOffer). Spec 2026-11-10-avisame-y-segundo-recordatorio, caso 3.
export default function AvisameJoin({
  slug,
  pal,
  color,
  onVerified,
}: {
  slug: string
  pal: ChatPalette
  color: string
  onVerified: (portalToken: string, name: string) => void
}) {
  const [supported, setSupported] = useState(false)
  const [open, setOpen] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    let alive = true
    Promise.resolve(detectNotifyState()).then((s) => {
      // Solo donde los avisos sí funcionan y aún no están activados.
      if (alive) setSupported(s === 'off')
    })
    return () => {
      alive = false
    }
  }, [])

  if (!supported || dismissed) return null
  if (open) return <InlineJoin slug={slug} color={color} onBrand={pal.onBrand} pal={pal} onVerified={onVerified} />

  return (
    <div className="mt-2.5 max-w-[82%] rounded-lg p-3 shadow-sm" style={{ background: pal.incoming, color: pal.text }}>
      <p className="flex items-center gap-2 text-sm font-semibold">
        <BellRing size={16} style={{ color }} /> ¿Te aviso por aquí de esto y de las promos?
      </p>
      <p className="mt-0.5 text-xs" style={{ color: pal.meta }}>Solo tu nombre y tu WhatsApp, y te llega al celular.</p>
      <div className="mt-2 flex gap-2">
        <button type="button" onClick={() => setOpen(true)}
          className="press rounded-full px-4 py-2 text-sm font-semibold"
          style={{ background: color, color: pal.onBrand }}>
          🔔 Avísame
        </button>
        <button type="button" onClick={() => setDismissed(true)} className="rounded-full px-3 py-2 text-sm"
          style={{ color: pal.meta }}>
          Ahora no
        </button>
      </div>
    </div>
  )
}
