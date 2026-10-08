import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import Honeypot from '@/components/Honeypot'
import CodeWait from '@/components/CodeWait'
import { verifyError } from '@/lib/codeMessages'
import api, { getApiError } from '@/lib/api'
import SEO from '@/components/SEO'
import { useNativeViewport } from '@/lib/useNativeViewport'
import { readAccountToken, readRecentChats, saveAccountToken } from '@/lib/customerAccount'
import CustomerChatList from '@/components/CustomerChatList'
import ChatAvatar from '@/components/ChatAvatar'
import { useMyBusinesses, type MyBusiness } from '@/lib/customerChats'
import { Gift, LogOut, MessageCircle, Search } from 'lucide-react'

// /mi — la app del cliente: entra con su número + un código por WhatsApp
// (backend: services/customer_account.py). Se usa como WhatsApp (pedido del
// dueño 2026-10-05): una lista de chats, uno por negocio, con el último
// mensaje y globito de no leídos; al tocar uno se abre su chat a pantalla
// completa (/c/:token). Abajo, Chats y Descubrir.

interface DiscoverBusiness {
  slug: string
  name: string
  logo_url: string
  color: string
  city: string
  category: string
  tagline: string
  reward: string | null
}

export default function MyAccountPage() {
  const [token, setToken] = useState<string | null>(readAccountToken)
  useNativeViewport('#111b21')
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

  // Sin entrar con su número: los chats que ya abrió en este celular (llegó por
  // el link de WhatsApp), como la lista de WhatsApp. "Entrar" muestra todos.
  const [recent] = useState(readRecentChats)
  const [showLogin, setShowLogin] = useState(false)

  const onToken = (t: string | null) => {
    saveAccountToken(t)
    setToken(t)
  }

  return (
    <>
      <SEO title="Mis negocios — IaRadio" noIndex />
      <div className="min-h-screen bg-[#111b21] px-4 pb-16 text-white" style={{ paddingTop: 'max(2rem, env(safe-area-inset-top, 0px))' }}>
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
          ) : recent.length && !showLogin ? (
            <RecentChats chats={recent} onLogin={() => setShowLogin(true)} />
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
  const [trap, setTrap] = useState('')
  const [step, setStep] = useState<'phone' | 'code'>('phone')
  const [sentAt, setSentAt] = useState(0)
  const [busy, setBusy] = useState(false)
  const [info, setInfo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const askCode = async () => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post('/public/me/code', { phone, website: trap })
      setInfo(data.message)
      setStep('code')
      setSentAt(Date.now())
    } catch (err) {
      setError(getApiError(err, 'No se pudo mandar el código'))
    } finally {
      setBusy(false)
    }
  }

  // Con los 6 dígitos (pegados o tecleados) entra solo, sin buscar el botón.
  const [triedCode, setTriedCode] = useState('')
  useEffect(() => {
    if (step === 'code' && code.length === 6 && code !== triedCode && !busy) {
      setTriedCode(code)
      void verify()
    }
    // verify lee el estado del momento; solo debe dispararse al completar el código.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, step])

  const verify = async () => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post('/public/me/verify', { phone, code })
      onToken(data.token)
    } catch (err) {
      setError(verifyError(err))
      setCode('')
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
        <Honeypot value={trap} onChange={setTrap} />
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
            <CodeWait sentAt={sentAt} muted="rgba(255,255,255,.6)" accent={'#a5b4fc'} onResend={() => { setCode(''); void askCode() }} />
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
      <p className="mt-6 text-center text-xs text-white/40">
        Al entrar aceptas el{' '}
        <a href="/privacy" className="underline">
          aviso de privacidad
        </a>
        .
      </p>
    </main>
  )
}

function Businesses({ token, onLogout }: { token: string; onLogout: () => void }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { data, isLoading, error } = useMyBusinesses(token, onLogout)

  const logout = () => {
    qc.removeQueries({ queryKey: ['my-businesses'] })
    onLogout()
  }
  const [tab, setTab] = useState<'chats' | 'discover'>('chats')

  return (
    <main className="pb-24">
      <div className="mt-2 flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">{tab === 'chats' ? 'Chats' : 'Descubrir'}</h1>
        <button onClick={logout} aria-label="Salir" className="inline-flex items-center gap-1.5 text-sm text-white/50 hover:text-white">
          <LogOut size={16} /> Salir
        </button>
      </div>

      {tab === 'discover' ? (
        <Discover token={token} />
      ) : (
        <>
          {data && data.businesses.length === 0 && (
            <div className="mt-10 text-center text-white/60">
              <p>Todavía no tienes chats con ningún negocio.</p>
              <button onClick={() => setTab('discover')} className="mt-3 font-semibold text-indigo-300">
                Descubre negocios cerca de ti
              </button>
            </div>
          )}
          <div className="mt-3 -mx-4">
            <CustomerChatList businesses={data?.businesses} isLoading={isLoading} error={error} onOpen={(path) => navigate(path)} />
          </div>
        </>
      )}

      {/* Abajo, como la barra de WhatsApp. */}
      <nav
        className="fixed inset-x-0 bottom-0 z-20 border-t border-white/10 bg-[#111b21]/95 backdrop-blur"
        style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
      >
        <div className="mx-auto grid max-w-lg grid-cols-2">
          {(
            [
              ['chats', 'Chats', MessageCircle],
              ['discover', 'Descubrir', Search],
            ] as const
          ).map(([key, label, Icon]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex flex-col items-center gap-0.5 py-2.5 text-xs font-semibold ${tab === key ? 'text-white' : 'text-white/45'}`}
            >
              <Icon size={22} />
              {label}
            </button>
          ))}
        </div>
      </nav>
    </main>
  )
}

// Otros negocios IaRadio: el cliente se une y les escribe gratis, sin
// WhatsApp (backend: /public/me/discover y /connect).
function Discover({ token }: { token: string }) {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [term, setTerm] = useState('')
  const [joining, setJoining] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const headers = { Authorization: `Bearer ${token}` }

  useEffect(() => {
    const t = setTimeout(() => setTerm(q.trim()), 350)
    return () => clearTimeout(t)
  }, [q])

  const { data, isLoading } = useQuery<{ businesses: DiscoverBusiness[] }>({
    queryKey: ['discover', token, term],
    queryFn: () => api.get('/public/me/discover', { headers, params: { q: term } }).then((r) => r.data),
  })

  const join = async (slug: string) => {
    setJoining(slug)
    setError(null)
    try {
      const { data: out } = await api.post('/public/me/connect', { slug }, { headers })
      navigate(out.portal_path)
    } catch (err) {
      setError(getApiError(err, 'No se pudo unir a este negocio'))
      setJoining(null)
    }
  }

  return (
    <div className="mt-5">
      <div className="relative">
        <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/40" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Busca: tacos, estética, tu ciudad…"
          className="w-full rounded-2xl border border-white/15 bg-white/5 py-3 pl-11 pr-4 text-white placeholder-white/30 focus:border-indigo-400 focus:outline-none"
        />
      </div>
      <p className="mt-3 text-xs text-white/40">
        Escríbele gratis a cualquier negocio, sin WhatsApp. Al unirte, el negocio podrá mandarte avisos y promociones.
      </p>
      {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
      {isLoading && <p className="mt-6 text-white/50">Buscando…</p>}
      {data && data.businesses.length === 0 && (
        <p className="mt-6 text-white/60">{term ? 'No encontramos negocios con esa búsqueda.' : 'Todavía no hay otros negocios cerca.'}</p>
      )}
      <div className="mt-4 space-y-3">
        {data?.businesses.map((b) => (
          <div key={b.slug} className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
            <div className="flex items-center gap-3">
              <ChatAvatar name={b.name} logo={b.logo_url} color={b.color} size={48} />
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{b.name}</p>
                <p className="truncate text-xs text-white/50">{[b.city, b.tagline].filter(Boolean).join(' · ')}</p>
              </div>
            </div>
            {b.reward && (
              <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-white/70">
                <Gift size={13} style={{ color: b.color }} /> Tarjeta de cliente: {b.reward}
              </p>
            )}
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => void join(b.slug)}
                disabled={joining !== null}
                className="flex-1 rounded-xl py-2.5 text-sm font-semibold text-white disabled:opacity-50"
                style={{ background: b.color }}
              >
                {joining === b.slug ? 'Un momento…' : 'Unirme y escribir'}
              </button>
              <a
                href={`/sitio/${b.slug}`}
                className="rounded-xl border border-white/15 px-4 py-2.5 text-sm font-semibold text-white/80"
              >
                Ver página
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}


// Chats de este celular sin haber entrado con su número.
function RecentChats({ chats, onLogin }: { chats: ReturnType<typeof readRecentChats>; onLogin: () => void }) {
  const navigate = useNavigate()
  const businesses: MyBusiness[] = chats.map((c) => ({
    portal_path: c.portal_path, name: c.name, logo_url: c.logo_url, color: c.color, city: '',
    loyalty: null, next_appointment: null, coupons: 0, last_message: null,
  }))
  return (
    <main className="pb-16">
      <h1 className="mt-2 text-2xl font-bold tracking-tight">Chats</h1>
      <div className="mt-3 -mx-4">
        <CustomerChatList businesses={businesses} onOpen={(path) => navigate(path)} />
      </div>
      <button onClick={onLogin} className="mt-6 w-full rounded-2xl border border-white/10 px-4 py-3.5 text-left text-sm text-white/70 hover:bg-white/[0.04]">
        <span className="font-semibold text-white">¿Eres cliente de más negocios?</span>
        <br />
        Entra con tu número y ve todos tus chats en un solo lugar.
      </button>
    </main>
  )
}
