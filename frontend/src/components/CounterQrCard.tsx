import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import QRCode from 'qrcode'
import api from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { Download, Printer, QrCode } from 'lucide-react'

// QR de mostrador: el cliente lo escanea, se registra con su WhatsApp
// (confirmado con un código) y entra a su tarjeta — el primer contacto sin
// tener que escribirle al negocio por WhatsApp. Backend: api/v1/join.py.

const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)

export default function CounterQrCard() {
  const { user } = useAuth()
  const [qr, setQr] = useState<string | null>(null)
  const { data: status } = useQuery<{ available: boolean }>({
    queryKey: ['account-status'],
    queryFn: () => api.get('/public/me/status').then((r) => r.data),
  })
  const url = user?.slug ? `${window.location.origin}/q/${user.slug}` : null
  const loyalty = user?.loyalty_config?.enabled && user.loyalty_config.reward ? user.loyalty_config : null

  useEffect(() => {
    if (!url) return
    QRCode.toDataURL(url, { width: 640, margin: 1, errorCorrectionLevel: 'M' }).then(setQr).catch(() => setQr(null))
  }, [url])

  const printPoster = () => {
    if (!qr || !user) return
    const name = escapeHtml(user.business_name || 'Nuestro negocio')
    const pitch = loyalty
      ? `Escanea y gana tu primer sello 🎁<br><small>Junta ${loyalty.stamps_required} y te llevas: ${escapeHtml(loyalty.reward)}</small>`
      : 'Escanea y hazte cliente<br><small>Agenda, pide y recibe promociones desde tu celular</small>'
    const w = window.open('', '_blank')
    if (!w) return
    w.document.write(`<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Cartel QR — ${name}</title>
<style>
  @page { size: letter; margin: 18mm }
  body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; text-align: center; color: #111; margin: 0 }
  h1 { font-size: 42px; margin: 24px 0 8px }
  p { font-size: 30px; font-weight: 700; margin: 16px 0 }
  small { display: block; font-size: 20px; font-weight: 500; color: #444; margin-top: 8px }
  img { width: 120mm; height: 120mm; margin: 12px auto; display: block }
  footer { font-size: 14px; color: #777; margin-top: 18px }
</style></head><body>
<h1>${name}</h1><p>${pitch}</p><img src="${qr}" alt="QR"><footer>Apunta la cámara de tu celular al código</footer>
<script>window.onload = () => { window.print() }</script></body></html>`)
    w.document.close()
  }

  return (
    <div className="rounded-xl bg-card p-6 shadow-sm border border-border space-y-4">
      <div className="flex items-center gap-2">
        <QrCode className="h-5 w-5 text-brand-500" />
        <h2 className="text-base font-semibold text-foreground">QR de mostrador</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Pega este cartel en tu mostrador. Tus clientes lo escanean, se registran con su WhatsApp (les llega un código
        para confirmar) y entran directo a su tarjeta{loyalty ? ' con su primer sello de regalo' : ''}. Quedan en tus
        Contactos, sin que tengas que escribirles primero.
      </p>

      {!url ? (
        <p className="text-sm text-foreground">
          Primero elige el link de tu página en{' '}
          <Link to="/app/widget" className="font-medium text-brand-500 underline">
            Widget de chat
          </Link>
          .
        </p>
      ) : (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          {qr && <img src={qr} alt="QR de tu negocio" className="h-36 w-36 rounded-lg border border-border bg-white p-1" />}
          <div className="space-y-2">
            <p className="break-all text-xs text-muted-foreground">{url}</p>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={printPoster}
                disabled={!qr}
                className="inline-flex items-center gap-1.5 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
              >
                <Printer className="h-4 w-4" /> Imprimir cartel
              </button>
              {qr && (
                <a
                  href={qr}
                  download={`qr-${user?.slug}.png`}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-muted"
                >
                  <Download className="h-4 w-4" /> Descargar QR
                </a>
              )}
            </div>
            {status && !status.available && (
              <p className="text-xs text-amber-600">
                El registro se enciende cuando Meta apruebe el mensaje con el código; mientras, el QR muestra "Muy pronto".
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
