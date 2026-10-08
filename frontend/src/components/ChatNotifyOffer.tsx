import { useEffect, useRef, useState } from 'react'
import { BellRing, Loader2 } from 'lucide-react'
import api from '@/lib/api'
import type { ChatPalette } from '@/lib/chatLook'
import { detectNotifyState, enablePush, type NotifyState } from '@/lib/webPushClient'

// Recién confirmada la cita en el chat: "¿Te aviso un día antes?". Es el mejor
// momento para pedir permiso (hay una razón concreta), y el recordatorio por
// aviso web es gratis — si no, sale por WhatsApp (cobrado) o no sale.
export default function ChatNotifyOffer({ token, pal, color }: { token: string; pal: ChatPalette; color: string }) {
  const [state, setState] = useState<NotifyState>('loading')
  const [publicKey, setPublicKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [stamped, setStamped] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  // Carga después del mensaje de la cita: que el chat baje para que se vea.
  const visible = !dismissed && ['off', 'on'].includes(state)
  useEffect(() => {
    if (visible) rootRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [visible, state])

  useEffect(() => {
    let alive = true
    Promise.all([
      Promise.resolve(detectNotifyState()),
      api.get(`/public/portal/${token}`).then((r) => r.data?.push).catch(() => null),
    ]).then(([s, push]) => {
      if (!alive) return
      if (!push?.available || !push.public_key) return setState('unsupported')
      setPublicKey(push.public_key)
      setState(s)
    })
    return () => {
      alive = false
    }
  }, [token])

  const enable = async () => {
    setBusy(true)
    try {
      const out = await enablePush(token, publicKey)
      setState(out.state)
      setStamped(out.stamped)
    } catch {
      setState('off')
    } finally {
      setBusy(false)
    }
  }

  if (!visible) return null

  return (
    <div ref={rootRef} className="mt-2.5 max-w-[82%] rounded-lg p-3 shadow-sm" style={{ background: pal.incoming, color: pal.text }}>
      {state === 'on' ? (
        <p className="text-sm">
          🔔 Listo, te aviso un día antes de tu cita.{stamped ? ' ¡Y ganaste un sello de regalo! 🎁' : ''}
        </p>
      ) : (
        <>
          <p className="flex items-center gap-2 text-sm font-semibold">
            <BellRing size={16} style={{ color }} /> ¿Te aviso un día antes de tu cita?
          </p>
          <p className="mt-0.5 text-xs" style={{ color: pal.meta }}>Te llega al celular, sin abrir nada.</p>
          <div className="mt-2 flex gap-2">
            <button type="button" onClick={() => void enable()} disabled={busy}
              className="press flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold disabled:opacity-50"
              style={{ background: color, color: pal.onBrand }}>
              {busy && <Loader2 size={14} className="animate-spin" />} Sí, avísame
            </button>
            <button type="button" onClick={() => setDismissed(true)} className="rounded-full px-3 py-2 text-sm"
              style={{ color: pal.meta }}>
              Ahora no
            </button>
          </div>
        </>
      )}
    </div>
  )
}
