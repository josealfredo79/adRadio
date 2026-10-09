import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
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

export default function PageBuilderModal({ onClose }: { onClose: () => void }) {
  const { user, setUser } = useAuth()
  const { data: site } = useQuery<SiteForChat>({
    queryKey: ['landing-chat', SLUG],
    queryFn: () => api.get(`/public/site/${SLUG}`).then((r) => r.data),
    staleTime: 10 * 60 * 1000,
  })

  if (!user || !site) return null

  const close = () => {
    onClose()
    api.get('/me').then((r) => setUser(r.data)).catch(() => {})
  }

  return createPortal(
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
  )
}
