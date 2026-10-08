import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import api, { getApiError } from '@/lib/api'
import { saveAccountToken } from '@/lib/customerAccount'
import { readRef } from '@/lib/referral'
import Honeypot from '@/components/Honeypot'
import CodeWait from '@/components/CodeWait'
import { verifyError } from '@/lib/codeMessages'
import type { ChatPalette } from '@/lib/chatLook'

// Registro sin salir del chat: cuando el bot necesita sus datos para agendar o
// pedir, aquí mismo pide nombre y WhatsApp, manda el código y lo verifica (el
// mismo /public/join/{slug} del QR). Al terminar, el chat sigue ya como cliente
// verificado — antes lo mandaba a otra página y ahí se perdían clientes.
export default function InlineJoin({
  slug,
  color,
  onBrand,
  pal,
  onVerified,
}: {
  slug: string
  color: string
  onBrand: string
  pal: ChatPalette
  onVerified: (portalToken: string, name: string) => void
}) {
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [trap, setTrap] = useState('')
  const [step, setStep] = useState<'form' | 'code'>('form')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [triedCode, setTriedCode] = useState('')
  const [sentAt, setSentAt] = useState(0)
  const codeRef = useRef<HTMLInputElement>(null)

  const askCode = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/public/join/${slug}/code`, { name, phone, website: trap })
      setStep('code')
      setSentAt(Date.now())
      setTimeout(() => codeRef.current?.focus(), 50)
    } catch (err) {
      setError(getApiError(err, 'No se pudo mandar el código'))
    } finally {
      setBusy(false)
    }
  }

  const verify = async (value: string) => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post(`/public/join/${slug}/verify`, { name, phone, code: value, ref: readRef(slug) })
      saveAccountToken(data.account_token)
      const token = String(data.portal_path || '').replace(/^\/c\//, '')
      onVerified(token, name.trim().split(/\s+/)[0] || '')
    } catch (err) {
      setError(verifyError(err))
      setCode('')
      setBusy(false)
    }
  }

  // Con los 6 dígitos (pegados o tecleados) entra solo.
  useEffect(() => {
    if (step === 'code' && code.length === 6 && code !== triedCode && !busy) {
      setTriedCode(code)
      void verify(code)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, step])

  const canSend = name.trim().length >= 2 && phone.replace(/\D/g, '').length >= 10
  const field = 'w-full rounded-lg px-3 py-2.5 text-base outline-none'
  const fieldStyle = { background: pal.field === '#ffffff' ? '#f0f2f5' : pal.field, color: pal.text }

  return (
    <form
      className="relative mt-1.5 max-w-[82%] space-y-2 rounded-lg p-3 shadow-sm"
      style={{ background: pal.incoming, color: pal.text }}
      onSubmit={(e) => {
        e.preventDefault()
        if (step === 'form') void askCode()
        else if (code.length === 6) void verify(code)
      }}
    >
      <Honeypot value={trap} onChange={setTrap} />
      {step === 'form' ? (
        <>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Tu nombre" autoComplete="given-name"
            maxLength={100} className={field} style={fieldStyle} aria-label="Tu nombre" />
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Tu WhatsApp (10 dígitos)" type="tel"
            inputMode="tel" autoComplete="tel" maxLength={20} className={field} style={fieldStyle} aria-label="Tu WhatsApp" />
          <button type="submit" disabled={!canSend || busy}
            className="press flex w-full items-center justify-center gap-2 rounded-full py-2.5 text-sm font-semibold disabled:opacity-50"
            style={{ background: color, color: onBrand }}>
            {busy && <Loader2 size={16} className="animate-spin" />} Mandarme el código por WhatsApp
          </button>
        </>
      ) : (
        <>
          <p className="text-sm">Te mandamos un código por WhatsApp al {phone}. Escríbelo aquí 👇</p>
          <input ref={codeRef} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder="123456" inputMode="numeric" autoComplete="one-time-code" maxLength={6}
            className={`${field} text-center text-xl tracking-[0.4em]`} style={fieldStyle} aria-label="Código" />
          <CodeWait sentAt={sentAt} muted={pal.meta} accent={color} onResend={() => { setCode(''); void askCode() }} />
          <div className="flex items-center justify-between text-xs" style={{ color: pal.meta }}>
            <button type="button" className="underline" onClick={() => { setStep('form'); setCode(''); setError(null) }}>
              Cambiar número
            </button>
            {busy && <Loader2 size={14} className="animate-spin" />}
          </div>
        </>
      )}
      {error && <p className="text-xs text-rose-500">{error}</p>}
      <p className="text-[11px] leading-snug" style={{ color: pal.meta }}>
        Solo lo usamos para confirmarte. Nada de spam.
      </p>
    </form>
  )
}
