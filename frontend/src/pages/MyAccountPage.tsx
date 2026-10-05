import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import api, { getApiError } from '@/lib/api'
import SEO from '@/components/SEO'
import { readAccountToken, saveAccountToken } from '@/lib/customerAccount'
import { CalendarDays, ChevronRight, LogOut, Stamp, Ticket } from 'lucide-react'

// /mi — la app del cliente: entra con su número + un código por WhatsApp
// (backend: services/customer_account.py) y ve todos los negocios IaRadio
// donde es cliente; cada tarjeta lo lleva al portal de ese negocio.

const TZ = 'America/Mexico_City'

interface MyBusiness {
  portal_path: string
  name: string
  logo_url: string
  color: string
  city: string
  loyalty: { stamps: number; required: number; reward: string; rewards_ready: number } | null
  next_appointment: { service: string; scheduled_at: string } | null
  coupons: number
}

const fmtWhen = (iso: string) =>
  new Intl.DateTimeFormat('es-MX', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', timeZone: TZ }).format(
    new Date(iso)
  )

export default function MyAccountPage() {
  const [token, setToken] = useState<string | null>(readAccountToken)
  const { data: status } = useQuery<{ available: boolean }>({
    queryKey: ['account-status'],
    queryFn: () => api.get('/public/me/status').then((r) => r.data),
    enabled: !token,
  })

  // "Agregar a inicio" instala esta página como la app IaRadio del cliente.
  useEffect(() => {
    const link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]')
    const previous = link?.href
    if (link) link.href = '/mi.webmanifest'
    return () => {
      if (link && previous) link.href = previous
    }
  }, [])

  const onToken = (t: string | null) => {
    saveAccountToken(t)
    setToken(t)
  }

  return (
    <>
      <SEO title="Mis negocios — IaRadio" noIndex />
      <div className="min-h-screen bg-[#06060f] px-4 pb-16 pt-8 text-white">
        <div className="mx-auto max-w-lg">
          <p className="text-sm font-semibold tracking-wide text-indigo-300">IaRadio</p>
          {token ? (
            <Businesses token={token} onLogout={() => onToken(null)} />
          ) : status && !status.available ? (
            <main className="mt-6">
              <h1 className="text-3xl font-bold tracking-tight">Muy pronto</h1>
              <p className="mt-3 text-[15px] leading-relaxed text-white/60">
                Aquí vas a ver todos los negocios donde eres cliente. Mientras, usa el link que te mandó cada negocio por WhatsApp.
              </p>
            </main>
          ) : (
            <Login onToken={onToken} />
          )}
        </div>
      </div>
    </>
  )
}

function Login({ onToken }: { onToken: (t: string) => void }) {
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [step, setStep] = useState<'phone' | 'code'>('phone')
  const [busy, setBusy] = useState(false)
  const [info, setInfo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const askCode = async () => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post('/public/me/code', { phone })
      setInfo(data.message)
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
      const { data } = await api.post('/public/me/verify', { phone, code })
      onToken(data.token)
    } catch (err) {
      setError(getApiError(err, 'Código incorrecto'))
    } finally {
      setBusy(false)
    }
  }

  const input =
    'w-full rounded-2xl border border-white/15 bg-white/5 px-4 py-3.5 text-lg text-white placeholder-white/30 focus:border-indigo-400 focus:outline-none'

  return (
    <main className="mt-6">
      <h1 className="text-3xl font-bold tracking-tight">Todos tus negocios, en un solo lugar</h1>
      <p className="mt-3 text-[15px] leading-relaxed text-white/60">
        Tus sellos, citas, cupones y promociones de cada negocio donde eres cliente. Entra con tu número de WhatsApp.
      </p>

      <form
        className="mt-8 space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          void (step === 'phone' ? askCode() : verify())
        }}
      >
        <label className="block text-sm text-white/60">Tu número de WhatsApp</label>
        <input
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="55 1234 5678"
          disabled={step === 'code'}
          className={input}
        />
        {step === 'code' && (
          <>
            <p className="pt-2 text-sm text-white/60">{info}</p>
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
          disabled={busy || (step === 'phone' ? phone.replace(/\D/g, '').length < 10 : code.length !== 6)}
          className="w-full rounded-2xl bg-indigo-500 py-3.5 text-base font-semibold text-white disabled:opacity-40"
        >
          {busy ? 'Un momento…' : step === 'phone' ? 'Mandarme el código' : 'Entrar'}
        </button>
        {step === 'code' && (
          <button
            type="button"
            onClick={() => {
              setStep('phone')
              setCode('')
              setInfo(null)
            }}
            className="w-full py-2 text-sm text-white/50"
          >
            Cambiar número
          </button>
        )}
      </form>
    </main>
  )
}

function Businesses({ token, onLogout }: { token: string; onLogout: () => void }) {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery<{ businesses: MyBusiness[] }>({
    queryKey: ['my-businesses', token],
    queryFn: () => api.get('/public/me/businesses', { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.data),
    retry: false,
  })

  // Sesión vencida o inválida: de vuelta a entrar con el número.
  useEffect(() => {
    const status = (error as { response?: { status?: number } } | null)?.response?.status
    if (status === 401) onLogout()
  }, [error, onLogout])

  const logout = () => {
    qc.removeQueries({ queryKey: ['my-businesses'] })
    onLogout()
  }

  return (
    <main className="mt-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Tus negocios</h1>
        <button onClick={logout} className="inline-flex items-center gap-1.5 text-sm text-white/50 hover:text-white">
          <LogOut size={16} /> Salir
        </button>
      </div>

      {isLoading && <p className="mt-8 text-white/50">Cargando…</p>}
      {error && <p className="mt-8 text-rose-400">{getApiError(error, 'No se pudieron cargar tus negocios')}</p>}
      {data && data.businesses.length === 0 && (
        <p className="mt-8 text-white/60">Todavía no eres cliente de ningún negocio con IaRadio.</p>
      )}

      <div className="mt-6 space-y-3">
        {data?.businesses.map((b) => (
          <Link
            key={b.portal_path}
            to={b.portal_path}
            className="block rounded-2xl border border-white/10 bg-white/[0.04] p-4 transition-colors hover:bg-white/[0.07]"
          >
            <div className="flex items-center gap-3">
              {b.logo_url ? (
                <img src={b.logo_url} alt="" className="h-12 w-12 rounded-xl object-cover" />
              ) : (
                <div
                  className="flex h-12 w-12 items-center justify-center rounded-xl text-lg font-bold"
                  style={{ background: `linear-gradient(135deg, ${b.color}, ${b.color}99)` }}
                >
                  {(b.name || '?')[0].toUpperCase()}
                </div>
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{b.name}</p>
                {b.city && <p className="text-xs text-white/50">{b.city}</p>}
              </div>
              <ChevronRight size={20} className="text-white/40" />
            </div>

            {b.loyalty && (
              <div className="mt-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="inline-flex items-center gap-1.5 text-white/70">
                    <Stamp size={14} style={{ color: b.color }} />
                    {b.loyalty.rewards_ready > 0 ? `🎁 ¡Premio listo! ${b.loyalty.reward}` : `${b.loyalty.stamps} de ${b.loyalty.required} sellos · ${b.loyalty.reward}`}
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(100, (b.loyalty.stamps / b.loyalty.required) * 100)}%`,
                      background: b.color,
                    }}
                  />
                </div>
              </div>
            )}

            {(b.next_appointment || b.coupons > 0) && (
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                {b.next_appointment && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.06] px-2.5 py-1 text-white/80">
                    <CalendarDays size={13} /> {b.next_appointment.service} · {fmtWhen(b.next_appointment.scheduled_at)}
                  </span>
                )}
                {b.coupons > 0 && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.06] px-2.5 py-1 text-white/80">
                    <Ticket size={13} /> {b.coupons} {b.coupons === 1 ? 'cupón' : 'cupones'}
                  </span>
                )}
              </div>
            )}
          </Link>
        ))}
      </div>
    </main>
  )
}
