import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import AgentChat from '@/components/AgentChat'
import MascotSmart from '@/components/MascotSmart'
import { getSiteTheme, isDarkTheme } from '@/pages/publicSite/theme'

// El bot ORIGINAL de IaRadio (el de /sitio/iaradio) flotando en la página
// principal, igual que en la página pública de un negocio: la mascota abajo a
// la derecha y, al tocarla, la hoja del chat. Todo enlace "#pruebalo" de la
// landing lo abre. El alta empieza cuando la persona toca "✨ Quiero probarlo gratis".
const SLUG = 'iaradio'
const HASH = '#pruebalo'

interface SiteForChat {
  advertiser_id: string
  business_name: string
  agent: string
  color: string
  greeting: string
  site_theme: string
  quick_asks?: { icon: string; text: string; action?: string }[] | null
}

export default function LandingSignup() {
  const [open, setOpen] = useState(false)
  const { data: site } = useQuery<SiteForChat>({
    queryKey: ['landing-chat', SLUG],
    queryFn: () => api.get(`/public/site/${SLUG}`).then((r) => r.data),
    staleTime: 10 * 60 * 1000,
  })

  useEffect(() => {
    if (window.location.hash === HASH) setOpen(true)
    const onClick = (e: MouseEvent) => {
      const link = (e.target as Element | null)?.closest?.(`a[href="${HASH}"]`)
      if (!link) return
      e.preventDefault()
      setOpen(true)
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [])

  if (!site) return null
  const theme = getSiteTheme(site.site_theme)
  const dark = isDarkTheme(theme)

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label={`Platicar con ${site.agent}`}
          className="press fixed right-4 z-30 flex items-end gap-1"
          style={{ bottom: 'calc(1rem + env(safe-area-inset-bottom, 0px))' }}
        >
          <span
            className="mb-6 max-w-[11rem] rounded-2xl rounded-br-sm px-3.5 py-2 text-left text-sm font-medium shadow-xl"
            style={{ background: dark ? '#1b1f2e' : '#fff', color: theme.text, border: `1px solid ${theme.cardBorder}` }}
          >
            ¡Hola! Soy {site.agent.split(' ')[0]} 👋 ¿Te ayudo?
          </span>
          <span
            className="flex h-[76px] w-[76px] items-center justify-center rounded-full bg-white shadow-2xl"
            style={{ boxShadow: `0 0 0 3px ${site.color}, 0 12px 32px ${site.color}66` }}
          >
            <MascotSmart mood="happy" size={70} color={site.color} />
          </span>
        </button>
      )}
      {open && (
        <AgentChat
          business={{
            advertiser_id: site.advertiser_id,
            name: site.business_name,
            agent: site.agent,
            color: site.color,
            greeting: site.greeting,
            quick_asks: site.quick_asks,
          }}
          theme={theme}
          voiceBase={`/public/site/${SLUG}`}
          prefill={null}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}
