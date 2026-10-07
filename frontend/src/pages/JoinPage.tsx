import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { captureRef, readRef } from '@/lib/referral'
import Honeypot from '@/components/Honeypot'
import { useQuery } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import SEO from '@/components/SEO'
import { useNativeViewport } from '@/lib/useNativeViewport'
import { saveAccountToken } from '@/lib/customerAccount'
import { Gift } from 'lucide-react'

// /q/:slug — a donde lleva el QR del mostrador (backend: api/v1/join.py). El
// cliente escribe nombre y WhatsApp, confirma con el código que le llega y
// entra directo a su tarjeta (el sello de bienvenida cae al abrirla).

interface JoinInfo {
  available: boolean
  business: { name: string; logo_url: string; color: string; city: string }
  loyalty: { required: number; reward: string } | null
}

export default function JoinPage() {
  const { slug } = useParams<{ slug: string }>()
  // Llegó con el link de recomendación de otro cliente (?r=): se guarda para el registro.
  useEffect(() => captureRef(slug), [slug])
  useNativeViewport('#06060f')
  const navigate = useNavigate()
  const { data, isLoading, isError } = useQuery<JoinInfo>({
    queryKey: ['join', slug],
    queryFn: () => api.get(`/public/join/${slug}`).then((r) => r.data),
    enabled: !!slug,
    retry: false,
  })
  const [name, setName] = useState('')
  const [trap, setTrap] = useState('')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [step, setStep] = useState<'form' | 'code'>('form')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (isLoading) return <div className="min-h-screen bg-[#06060f]" />
  if (isError || !data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#06060f] px-6 text-center text-white">
        <p className="text-xl font-semibold">No encontramos este negocio</p>
      </div>
    )
  }

  const { business, loyalty } = data
  const color = business.color

  const askCode = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/public/join/${slug}/code`, { name, phone, website: trap })
      setStep('code')
    } catch (err) {
      setError(getApiError(err, 'No se pudo mandar el código'))
    } finally {
      setBusy(false)
    }
  }

  const verify = async () => {
    setBusy(true)
    setError(null)
    try {
      const { data: out } = await api.post(`/public/join/${slug}/verify`, { name, phone, code, ref: readRef(slug) })
      saveAccountToken(out.account_token)
      navigate(out.portal_path, { replace: true })
    } catch (err) {
      setError(getApiError(err, 'Código incorrecto'))
      setBusy(false)
    }
  }

  const input =
    'w-full rounded-2xl border border-white/15 bg-white/5 px-4 py-3.5 text-lg text-white placeholder-white/30 focus:outline-none'
  const canSend = name.trim().length >= 2 && phone.replace(/\D/g, '').length >= 10

  return (
    <>
      <SEO title={`Únete a ${business.name}`} noIndex />
      <div className="min-h-screen bg-[#06060f] px-4 pb-16 text-white" style={{ paddingTop: 'max(2rem, env(safe-area-inset-top, 0px))' }}>
        <div className="mx-auto max-w-md">
          <header className="flex items-center gap-3">
            {business.logo_url ? (
              <img src={business.logo_url} alt="" className="h-12 w-12 rounded-xl object-cover" />
            ) : (
              <div
                className="flex h-12 w-12 items-center justify-center rounded-xl text-lg font-bold"
                style={{ background: `linear-gradient(135deg, ${color}, ${color}99)` }}
              >
                {(business.name || '?')[0].toUpperCase()}
              </div>
            )}
            <div>
              <p className="font-semibold">{business.name}</p>
              {business.city && <p className="text-xs text-white/50">{business.city}</p>}
            </div>
          </header>

          {!data.available ? (
            <main className="mt-10">
              <h1 className="text-3xl font-bold tracking-tight">Muy pronto</h1>
              <p className="mt-3 text-white/60">Aquí te vas a poder registrar como cliente de {business.name}.</p>
            </main>
          ) : (
            <main className="mt-10">
              {loyalty ? (
                <div className="rounded-2xl p-5" style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)` }}>
                  <p className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide opacity-90">
                    <Gift size={16} /> Regalo de bienvenida
                  </p>
                  <p className="mt-2 text-2xl font-bold leading-snug">Tu primer sello, gratis</p>
                  <p className="mt-1 text-sm opacity-90">
                    Junta {loyalty.required} y te llevas: {loyalty.reward}
                  </p>
                </div>
              ) : (
                <h1 className="text-3xl font-bold tracking-tight">Hazte cliente de {business.name}</h1>
              )}
              <p className="mt-4 text-[15px] leading-relaxed text-white/60">
                Agenda, pide y recibe promociones sin esperar respuesta. Te mandamos un código a tu WhatsApp para confirmar que eres tú.
              </p>

              <form
                className="mt-6 space-y-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  void (step === 'form' ? askCode() : verify())
                }}
              >
                <Honeypot value={trap} onChange={setTrap} />
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Tu nombre"
                  autoComplete="given-name"
                  disabled={step === 'code'}
                  maxLength={100}
                  className={input}
                />
                <input
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="Tu WhatsApp (10 dígitos)"
                  disabled={step === 'code'}
                  className={input}
                />
                {step === 'code' && (
                  <>
                    <p className="pt-1 text-sm text-white/60">Te mandamos un código por WhatsApp.</p>
                    <input
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={6}
                      value={code}
                      onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                      placeholder="Código de 6 dígitos"
                      autoFocus
                      className={`${input} tracking-[0.4em]`}
                    />
                  </>
                )}
                {error && <p className="text-sm text-rose-400">{error}</p>}
                <button
                  type="submit"
                  disabled={busy || (step === 'form' ? !canSend : code.length !== 6)}
                  className="w-full rounded-2xl py-3.5 text-base font-semibold text-white disabled:opacity-40"
                  style={{ background: color }}
                >
                  {busy ? 'Un momento…' : step === 'form' ? 'Mandarme el código' : 'Entrar a mi tarjeta'}
                </button>
              </form>
            </main>
          )}
        </div>
      </div>
    </>
  )
}
