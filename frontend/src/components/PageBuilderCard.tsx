import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import api from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import AgentChat from '@/components/AgentChat'
import { getSiteTheme } from '@/pages/publicSite/theme'

// El bot de IaRadio (el de /sitio/iaradio) en el panel: arma la página del
// dueño que aún no la tiene y la guarda en su cuenta, sin WhatsApp ni código.
const SLUG = 'iaradio'

interface SiteForChat {
  advertiser_id: string
  business_name: string
  agent: string
  color: string
  greeting: string
  site_theme: string
  quick_asks?: { icon: string; text: string; action?: string }[] | null
}

export default function PageBuilderCard() {
  const { user, setUser } = useAuth()
  const [open, setOpen] = useState(false)
  const { data: site } = useQuery<SiteForChat>({
    queryKey: ['landing-chat', SLUG],
    queryFn: () => api.get(`/public/site/${SLUG}`).then((r) => r.data),
    staleTime: 10 * 60 * 1000,
    enabled: open,
  })

  if (!user || user.role !== 'advertiser' || user.slug) return null

  const close = () => {
    setOpen(false)
    api.get('/me').then((r) => setUser(r.data)).catch(() => {})
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex w-full items-center gap-4 rounded-2xl border border-brand-200 bg-brand-50 p-5 text-left transition-shadow hover:shadow-md dark:border-brand-900 dark:bg-brand-950/30"
      >
        <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-brand-500 text-white">
          <Sparkles className="h-7 w-7" />
        </span>
        <span>
          <span className="block text-lg font-bold text-foreground">Arma tu página con IaRadio</span>
          <span className="block text-base text-muted-foreground">
            Cuéntale de tu negocio por voz o texto y en unos minutos tienes tu página, tu catálogo y tu bot listos.
          </span>
        </span>
      </button>
      {open && site && createPortal(
        <div className="relative z-[100]">
          <AgentChat
            business={{
              advertiser_id: site.advertiser_id,
              name: site.business_name,
              agent: site.agent,
              color: site.color,
              greeting: site.greeting,
              quick_asks: site.quick_asks,
            }}
            theme={getSiteTheme(site.site_theme)}
            voiceBase={`/public/site/${SLUG}`}
            prefill={null}
            ownerOnboarding={{ name: user.business_name }}
            onClose={close}
          />
        </div>,
        document.body,
      )}
    </>
  )
}
