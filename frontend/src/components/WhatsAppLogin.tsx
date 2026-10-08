import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import api, { getApiError, setAccessToken } from '@/lib/api'
import Honeypot from '@/components/Honeypot'
import CodeWait from '@/components/CodeWait'
import { verifyError } from '@/lib/codeMessages'

// Entrar al panel con WhatsApp y un código, sin contraseña: así entran los
// negocios que se dieron de alta en el chat de IaRadio (OnboardingFlow), y
// cualquier dueño con su WhatsApp en Configuración. Backend: /auth/whatsapp.
export default function WhatsAppLogin({ onDone }: { onDone: () => void }) {
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [trap, setTrap] = useState('')
  const [step, setStep] = useState<'phone' | 'code'>('phone')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sentAt, setSentAt] = useState(0)
  const [tried, setTried] = useState('')
  const codeRef = useRef<HTMLInputElement>(null)

  const askCode = async () => {
    setBusy(true)
    setError('')
    try {
      await api.post('/auth/whatsapp/code', { phone, website: trap })
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
    setError('')
    try {
      const { data } = await api.post('/auth/whatsapp/verify', { phone, code: value })
      setAccessToken(data.access_token)
      onDone()
    } catch (err) {
      setError(verifyError(err))
      setCode('')
      setBusy(false)
    }
  }

  useEffect(() => {
    if (step === 'code' && code.length === 6 && code !== tried && !busy) {
      setTried(code)
      void verify(code)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, step])

  const input = 'w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100'

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (step === 'phone') void askCode()
        else if (code.length === 6) void verify(code)
      }}
    >
      <Honeypot value={trap} onChange={setTrap} />
      {step === 'phone' ? (
        <div>
          <label htmlFor="wa-phone" className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">Tu WhatsApp</label>
          <input id="wa-phone" type="tel" inputMode="tel" autoComplete="tel" required value={phone} maxLength={20}
            onChange={(e) => setPhone(e.target.value)} className={input} placeholder="10 dígitos" />
          <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">Te mandamos un código por WhatsApp. Sin contraseñas.</p>
        </div>
      ) : (
        <div className="space-y-2">
          <label htmlFor="wa-code" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Código que te llegó al {phone}</label>
          <input id="wa-code" ref={codeRef} value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={6}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            className={`${input} text-center text-xl tracking-[0.4em]`} placeholder="123456" />
          <CodeWait sentAt={sentAt} muted="#6b7280" accent="#6d4aff" onResend={() => { setCode(''); void askCode() }} />
          <button type="button" className="text-xs text-brand-600 underline dark:text-brand-400" onClick={() => { setStep('phone'); setCode(''); setError('') }}>
            Cambiar número
          </button>
        </div>
      )}
      {error && <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">{error}</div>}
      <button type="submit" disabled={busy || (step === 'phone' ? phone.replace(/\D/g, '').length < 10 : code.length < 6)}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-500 py-2.5 text-sm font-medium text-white shadow transition-colors hover:bg-brand-600 disabled:opacity-60">
        {busy && <Loader2 size={16} className="animate-spin" />}
        {step === 'phone' ? 'Mandarme el código' : 'Entrar'}
      </button>
    </form>
  )
}
