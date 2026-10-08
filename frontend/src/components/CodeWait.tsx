import { useEffect, useState } from 'react'

// Mientras llega el código por WhatsApp: aviso de que puede tardar, cuenta
// regresiva y "Reenviar código" (el backend deja pedir otro cada 60 s). Visto
// 2026-10-07: el código salió de Meta en 1 s pero el celular lo recibió ~3 min
// después — sin aviso, el cliente cree que no funcionó.
const RESEND_AFTER_S = 60

export default function CodeWait({
  sentAt,
  onResend,
  muted,
  accent,
}: {
  sentAt: number
  onResend: () => void
  muted: string
  accent: string
}) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const left = Math.max(0, RESEND_AFTER_S - Math.floor((now - sentAt) / 1000))
  return (
    <div className="space-y-1 text-xs" style={{ color: muted }}>
      <p>Te llega en unos segundos por WhatsApp. A veces tarda hasta 2 minutos.</p>
      {left > 0 ? (
        <p>¿No te llegó? Puedes pedir otro en {left} s.</p>
      ) : (
        <button type="button" onClick={onResend} className="font-semibold underline" style={{ color: accent }}>
          Reenviar código
        </button>
      )}
    </div>
  )
}
